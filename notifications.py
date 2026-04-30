"""
SAAI v5.0 — Sistema de Notificaciones
Basado en "Un Millón al Año No Hace Daño" — Yoel Sardiñas

Estrategias del libro:
  E1 — Canal Lateral al Alza
  E2 — Canal Lateral a la Baja
  E3 — Saltos en Apertura

Soporta múltiples emails separados por coma en EMAIL_TO
Ejemplo: EMAIL_TO=email1@gmail.com,email2@gmail.com
"""

import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from analysis_engine import Alert, SignalDirection, SignalStrength, StrategyType


# ============================================================
# EMAIL HTML
# ============================================================

def format_email_html(alert: Alert) -> str:

    # Colores por dirección
    if alert.direction == SignalDirection.CALL:
        accent    = "#1a6b3c"
        bg_accent = "rgba(26,107,60,0.08)"
        emoji_dir = "CALL"
    elif alert.direction == SignalDirection.PUT:
        accent    = "#c8401a"
        bg_accent = "rgba(200,64,26,0.08)"
        emoji_dir = "PUT"
    else:
        accent    = "#b8860b"
        bg_accent = "rgba(184,134,11,0.08)"
        emoji_dir = "NEUTRAL"

    # Badge de estrategia
    strat_badges = {
        StrategyType.E1_CANAL_ALZA:       ("E1", "#1a6b3c"),
        StrategyType.E2_CANAL_BAJA:       ("E2", "#c8401a"),
        StrategyType.E3_SALTO_ALCISTA:    ("E3", "#1a3a6b"),
        StrategyType.E3_SALTO_BAJISTA:    ("E3", "#1a3a6b"),
        StrategyType.E3_CAMBIO_TENDENCIA: ("E3", "#b8860b"),
        StrategyType.SQUEEZE_CANAL:       ("NEUTRAL",  "#b8860b"),
    }
    badge_txt, badge_color = strat_badges.get(alert.strategy, ("?", "#888"))

    # Tendencia 1H
    trend_map = {
        "alcista_fuerte":  "ALCISTA FUERTE (20 > 40 > 100 > 200)",
        "alcista_parcial": "ALCISTA PARCIAL (mayoría alcista)",
        "bajista_fuerte":  "BAJISTA FUERTE (20 < 40 < 100 < 200)",
        "bajista_parcial": "BAJISTA PARCIAL (mayoría bajista)",
        "lateral":         "LATERAL (MAs entrelazadas)",
    }
    trend_1h    = trend_map.get(alert.ma.trend_1h,    alert.ma.trend_1h)
    trend_daily = trend_map.get(alert.ma.daily_trend, alert.ma.daily_trend)

    # Volatilidad BB 15min
    vol_colors = {"ALTA": "#1a6b3c", "MEDIA": "#b8860b", "BAJA": "#c8401a"}
    vol_color  = vol_colors.get(alert.bb.volatility_level, "#666")

    if alert.bb.price_above_upper:
        bb_status = f"HOT Precio SALIÓ banda superior — {alert.bb.bandwidth_pct_15m:.0f}% percentil"
    elif alert.bb.price_below_lower:
        bb_status = f"HOT Precio SALIÓ banda inferior — {alert.bb.bandwidth_pct_15m:.0f}% percentil"
    elif alert.bb.is_squeeze_15m:
        bb_status = f"NEUTRAL SQUEEZE — Explosión inminente"
    elif alert.bb.is_expanding_15m:
        bb_status = f"UP Expandiendo — {alert.bb.bandwidth_pct_15m:.0f}% percentil"
    else:
        bb_status = f"Normal — {alert.bb.bandwidth_pct_15m:.0f}% percentil"

    # Vela de confirmación
    candle_icons = {
        "extreme_bullish": "[vela] Vela ALCISTA EXTREMA",
        "extreme_bearish": "[vela] Vela BAJISTA EXTREMA",
        "normal_bullish":  "[vela] Vela Alcista Normal",
        "normal_bearish":  "[vela] Vela Bajista Normal",
        "doji":            "[vela] Doji",
    }
    candle_txt  = candle_icons.get(alert.bb.candle_type, alert.bb.candle_type)
    candle_body = f" ({alert.bb.candle_body_pct:.0f}% cuerpo)"

    # Canal lateral
    canal_txt = f"OK {alert.ma.lateral_days_1h} días" if alert.ma.is_lateral_1h else "No detectado"

    # Soporte / Resistencia
    sup_res = []
    if alert.ma.nearest_support:
        sup_res.append(f"Soporte: {alert.ma.nearest_support}")
    if alert.ma.nearest_resistance:
        sup_res.append(f"Resistencia: {alert.ma.nearest_resistance}")
    sup_res_txt = " | ".join(sup_res) if sup_res else "Sin niveles cercanos"

    # Puntos ciegos diario
    blind_html = ""
    if alert.ma.daily_blind_spots:
        items = "<br>".join([f'WARN {b}' for b in alert.ma.daily_blind_spots])
        blind_html = f"""
        <tr style="border-bottom:1px solid #eee;">
          <td style="padding:8px 12px;color:#b8860b;font-size:13px;">Puntos Ciegos Diario</td>
          <td style="padding:8px 12px;font-size:12px;color:#b8860b;font-weight:600;">{items}</td>
        </tr>"""

    # Eventos macro
    if alert.external_events:
        ev_html = "<br>".join([
            f'<span style="color:#b8860b;">{e["warning"]}</span>'
            for e in alert.external_events
        ])
    else:
        ev_html = '<span style="color:#1a6b3c;">Sin eventos macro — señal limpia</span>'

    # Confirmación BB 1H
    confirm_1h_txt = "OK BB 1H expandiendo también" if alert.bb.bb_expanding_1h \
                     else "WARN BB 1H pendiente de confirmar"

    # RSI
    rsi = alert.bb.rsi_15m
    if alert.bb.rsi_signal == "SOBRECOMPRADO":
        rsi_color = "#c8401a"
        rsi_txt   = f"PUT {rsi} — SOBRECOMPRADO (>70) — cuidado con CALL"
    elif alert.bb.rsi_signal == "SOBREVENDIDO":
        rsi_color = "#1a6b3c"
        rsi_txt   = f"CALL {rsi} — SOBREVENDIDO (<30) — cuidado con PUT"
    else:
        rsi_color = "#333"
        rsi_txt   = f"OK {rsi} — Zona neutral"

    # Sobreextensión
    if alert.bb.overextended:
        overext_txt = (
            f"WARN SÍ — precio {alert.bb.overextension_pct:.0f}% más allá de la banda "
            f"— alta probabilidad de reversión"
        )
    else:
        overext_txt = "OK No — precio dentro de rango normal"

    # Earnings
    if alert.earnings.get("has_earnings"):
        days = alert.earnings.get("days_away", 0)
        if days == 0:
            e_color = "#c8401a"
            e_icon  = "ALERT"
        elif days == 1:
            e_color = "#b8860b"
            e_icon  = "WARN"
        else:
            e_color = "#666"
            e_icon  = "[D]"
        earnings_html = (
            f'<span style="color:{e_color};font-weight:700;">'
            f'{e_icon} {alert.earnings["warning"]}</span>'
        )
    else:
        earnings_html = '<span style="color:#1a6b3c;">Sin earnings próximos — señal limpia</span>'

    # Agotamiento
    if alert.agotamiento.get("has_agotamiento"):
        signals_list = "".join([
            f'<li style="margin:4px 0;">{s}</li>'
            for s in alert.agotamiento.get("signals", [])
        ])
        agot_html = f"""
  <div style="background:#fff8f0;border-left:4px solid #b8860b;padding:16px 20px;margin-top:2px;">
    <div style="font-size:10px;letter-spacing:1.5px;color:#b8860b;margin-bottom:8px;
                text-transform:uppercase;">WARN Señales de Agotamiento</div>
    <ul style="margin:0;padding-left:18px;font-size:13px;color:#555;line-height:1.9;">
      {signals_list}
    </ul>
    <div style="margin-top:10px;font-size:12px;color:#b8860b;font-style:italic;">
      Del libro: "Nada sube para siempre y nada baja para siempre."<br>
      Si tienes posición abierta, considera protegerla o salir.
    </div>
  </div>"""
    else:
        agot_html = ""

    html = f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f5f2eb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<div style="max-width:620px;margin:0 auto;padding:24px;">

  <!-- HEADER -->
  <div style="background:#0d1117;color:white;padding:22px 24px;border-bottom:4px solid {accent};">
    <div style="font-size:10px;letter-spacing:2px;opacity:0.5;margin-bottom:6px;">
      SAAI v5.0 — SMART ALERT AI SYSTEM
    </div>
    <div style="display:flex;align-items:center;gap:12px;">
      <span style="background:{badge_color};color:white;padding:4px 10px;font-size:12px;
                   font-weight:800;border-radius:3px;">{badge_txt}</span>
      <span style="font-size:30px;font-weight:800;letter-spacing:-1px;">{alert.ticker}</span>
      <span style="font-size:13px;opacity:0.5;margin-left:4px;">[{alert.categoria}]</span>
    </div>
    <div style="font-size:11px;opacity:0.5;margin-top:6px;">{alert.timestamp}</div>
  </div>

  <!-- ESTRATEGIA -->
  <div style="background:{bg_accent};border-left:4px solid {accent};padding:16px 20px;margin-top:2px;">
    <div style="font-size:10px;letter-spacing:1.5px;color:{accent};margin-bottom:4px;
                text-transform:uppercase;">Estrategia Identificada</div>
    <div style="font-size:16px;font-weight:700;color:#1a1a18;margin-bottom:10px;">
      {alert.strategy.value}
    </div>
    <span style="background:{accent};color:white;padding:5px 14px;font-size:12px;
                 font-weight:700;letter-spacing:1px;">
      {emoji_dir} {alert.direction.value} {alert.strength.value}
    </span>
    <span style="margin-left:10px;font-size:12px;color:{accent};font-weight:600;">
      Score: {alert.score}/100
    </span>
  </div>

  <!-- PANORAMA COMPLETO — 3 TEMPORALIDADES -->
  <div style="background:white;padding:20px 24px;margin-top:2px;border:1px solid #e5e0d5;">
    <div style="font-size:10px;letter-spacing:1.5px;color:#999;margin-bottom:16px;
                text-transform:uppercase;">
      Panorama Completo — 3 Temporalidades del Libro
    </div>

    <table style="width:100%;border-collapse:collapse;">

      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:8px 12px;color:#666;font-size:13px;">Precio Actual</td>
        <td style="padding:8px 12px;font-size:14px;font-weight:700;">${alert.price}</td>
      </tr>

      <!-- MAs 1H — DECISIÓN -->
      <tr style="border-bottom:1px solid #eee;background:#f0f4ff;">
        <td style="padding:8px 12px;color:#1a3a6b;font-size:13px;font-weight:700;">
          [MAs] MAs 1H (DECISIÓN)
        </td>
        <td style="padding:8px 12px;font-size:13px;font-weight:700;color:#1a3a6b;">
          {trend_1h}
        </td>
      </tr>
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:8px 12px;color:#666;font-size:12px;">MA 20 / 40 / 100 / 200</td>
        <td style="padding:8px 12px;font-size:12px;">
          ${alert.ma.ma20_1h} / ${alert.ma.ma40_1h} / ${alert.ma.ma100_1h} / ${alert.ma.ma200_1h}
        </td>
      </tr>
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:8px 12px;color:#666;font-size:12px;">Canal Lateral 1H</td>
        <td style="padding:8px 12px;font-size:12px;">{canal_txt}</td>
      </tr>
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:8px 12px;color:#666;font-size:12px;">Soporte / Resistencia</td>
        <td style="padding:8px 12px;font-size:12px;">{sup_res_txt}</td>
      </tr>

      <!-- BB 15min — ENTRADA -->
      <tr style="border-bottom:1px solid #eee;background:#f0fff4;">
        <td style="padding:8px 12px;color:#1a6b3c;font-size:13px;font-weight:700;">
          [BB] BB 15min (ENTRADA)
        </td>
        <td style="padding:8px 12px;font-size:13px;font-weight:700;color:{vol_color};">
          {alert.bb.volatility_level} — {bb_status}
        </td>
      </tr>
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:8px 12px;color:#666;font-size:12px;">Banda Superior / Inferior</td>
        <td style="padding:8px 12px;font-size:12px;">${alert.bb.upper_15m} / ${alert.bb.lower_15m}</td>
      </tr>
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:8px 12px;color:#666;font-size:12px;">Vela Confirmación 15min</td>
        <td style="padding:8px 12px;font-size:12px;">{candle_txt}{candle_body}</td>
      </tr>
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:8px 12px;color:#666;font-size:12px;">RSI 14 (15min)</td>
        <td style="padding:8px 12px;font-size:12px;font-weight:600;color:{rsi_color};">{rsi_txt}</td>
      </tr>
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:8px 12px;color:#666;font-size:12px;">Sobreextensión BB</td>
        <td style="padding:8px 12px;font-size:12px;">{overext_txt}</td>
      </tr>
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:8px 12px;color:#666;font-size:12px;">Confirmación 1H</td>
        <td style="padding:8px 12px;font-size:12px;">{confirm_1h_txt}</td>
      </tr>

      <!-- Diario — CONTEXTO -->
      <tr style="border-bottom:1px solid #eee;background:#fffdf0;">
        <td style="padding:8px 12px;color:#b8860b;font-size:13px;font-weight:700;">
          [D] Diario (CONTEXTO)
        </td>
        <td style="padding:8px 12px;font-size:13px;color:#b8860b;">{trend_daily}</td>
      </tr>
      {blind_html}

      <!-- Eventos Macro -->
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:8px 12px;color:#666;font-size:12px;">Eventos Macro</td>
        <td style="padding:8px 12px;font-size:12px;">{ev_html}</td>
      </tr>

      <!-- Earnings -->
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:8px 12px;color:#666;font-size:12px;">Earnings</td>
        <td style="padding:8px 12px;font-size:12px;">{earnings_html}</td>
      </tr>

    </table>
  </div>

  <!-- AGOTAMIENTO (si aplica) -->
  {agot_html}

  <!-- EXPLICACIÓN DEL LIBRO -->
  <div style="background:#faf8f3;padding:20px 24px;margin-top:2px;border:1px solid #e5e0d5;">
    <div style="font-size:10px;letter-spacing:1.5px;color:#999;margin-bottom:12px;
                text-transform:uppercase;">
      📖 Metodología — Yoel Sardiñas
    </div>
    <div style="font-size:13px;line-height:2.0;color:#333;white-space:pre-line;">
      {alert.explanation}
    </div>
  </div>

  <!-- RECOMENDACIÓN -->
  <div style="background:{accent};color:white;padding:18px 24px;margin-top:2px;">
    <div style="font-size:10px;letter-spacing:1.5px;opacity:0.7;margin-bottom:8px;
                text-transform:uppercase;">Recomendación</div>
    <div style="font-size:15px;font-weight:700;line-height:1.8;white-space:pre-line;">
      {alert.recommendation}
    </div>
  </div>

  <!-- FOOTER -->
  <div style="padding:20px 24px;font-size:10px;color:#aaa;text-align:center;line-height:2.0;">
    SAAI v5.3 — Smart Alert AI System<br>
    "Un Millón al Año No Hace Daño" — Yoel Sardiñas<br><br>
    [MAs] MAs 1H → Decisión &nbsp;|&nbsp; [BB] BB 15min → Entrada &nbsp;|&nbsp; [D] Diario → Contexto<br><br>
    WARN Herramienta de análisis técnico. No garantiza resultados.<br>
    La decisión final siempre es del trader.<br>
    Confirmar en TC2000 antes de entrar.
  </div>

</div>
</body>
</html>"""

    return html


# ============================================================
# TEXTO PLANO (fallback)
# ============================================================

def format_sms_text(alert: Alert) -> str:
    emoji = "CALL" if alert.direction == SignalDirection.CALL \
            else "PUT" if alert.direction == SignalDirection.PUT else "NEUTRAL"

    txt = (
        f"{emoji} SAAI v5.0 — {alert.ticker} [{alert.categoria}]\n"
        f"{alert.timestamp}\n\n"
        f"📖 {alert.strategy.value}\n"
        f"🎯 {alert.direction.value} {alert.strength.value} | Score: {alert.score}/100\n\n"
        f"MAs 1H    (DECISIÓN): {alert.ma.trend_1h}\n"
        f"BB 15min  (ENTRADA):  {alert.bb.volatility_level} — {alert.bb.bandwidth_pct_15m:.0f}% percentil\n"
        f"Vela 15min:           {alert.bb.candle_type} ({alert.bb.candle_body_pct:.0f}% cuerpo)\n"
        f"Diario    (CONTEXTO): {alert.ma.daily_trend}\n"
        f"Precio: ${alert.price}\n"
    )

    if alert.ma.is_lateral_1h:
        txt += f"Canal lateral: {alert.ma.lateral_days_1h} días\n"

    if alert.ma.daily_warning:
        txt += f"\n{alert.ma.daily_warning}\n"

    if alert.warning:
        txt += f"\n{alert.warning}\n"

    txt += f"\n{alert.recommendation}"
    return txt


# ============================================================
# ENVÍO EMAIL — MÚLTIPLES DESTINATARIOS
# ============================================================

def send_email(alert: Alert) -> bool:
    try:
        gmail_user     = os.environ.get("GMAIL_USER")
        gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
        email_to_raw   = os.environ.get("EMAIL_TO", "")

        if not all([gmail_user, gmail_password, email_to_raw]):
            print("[Email] WARN Variables de Gmail no configuradas")
            return False

        recipients = [e.strip() for e in email_to_raw.split(",") if e.strip()]
        if not recipients:
            print("[Email] WARN No hay destinatarios configurados")
            return False

        msg = MIMEMultipart("alternative")

        emoji = "CALL" if alert.direction == SignalDirection.CALL \
                else "PUT" if alert.direction == SignalDirection.PUT else "NEUTRAL"

        msg["Subject"] = (
            f"{emoji} SAAI: {alert.ticker} [{alert.categoria}] — "
            f"{alert.direction.value} {alert.strength.value} — "
            f"{alert.strategy.value}"
        )
        msg["From"] = gmail_user
        msg["To"]   = ", ".join(recipients)

        msg.attach(MIMEText(format_sms_text(alert),  "plain"))
        msg.attach(MIMEText(format_email_html(alert), "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, recipients, msg.as_string())

        print(f"[Email] OK Enviado a: {', '.join(recipients)}")
        return True

    except Exception as e:
        print(f"[Email] ERROR Error: {e}")
        return False


# ============================================================
# ENVÍO SMS — TWILIO (OPCIONAL)
# ============================================================

def send_sms(alert: Alert) -> bool:
    try:
        from twilio.rest import Client

        sid         = os.environ.get("TWILIO_SID")
        token       = os.environ.get("TWILIO_TOKEN")
        from_number = os.environ.get("TWILIO_FROM")
        to_number   = os.environ.get("TWILIO_TO")

        if not all([sid, token, from_number, to_number]):
            return False
        if "placeholder" in str(sid).lower():
            return False

        client  = Client(sid, token)
        message = client.messages.create(
            body=format_sms_text(alert),
            from_=from_number,
            to=to_number,
        )
        print(f"[SMS] OK Enviado — SID: {message.sid}")
        return True

    except Exception as e:
        if "placeholder" not in str(e).lower():
            print(f"[SMS] ERROR Error: {e}")
        return False


# ============================================================
# ENVIAR TODOS LOS CANALES
# ============================================================

def send_alert(alert: Alert) -> dict:
    results = {
        "email": send_email(alert),
        "sms":   send_sms(alert),
    }
    print(
        f"[Notificaciones] "
        f"Email: {'OK' if results['email'] else 'ERROR'} | "
        f"SMS: {'OK' if results['sms'] else 'SKIP (no configurado)'}"
    )
    return results
