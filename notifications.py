"""
SAAI v4 — Sistema de Notificaciones
Compatible con analysis_engine v4

Soporta múltiples emails separados por coma en EMAIL_TO
Ejemplo: EMAIL_TO=email1@gmail.com,email2@gmail.com
"""

import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from analysis_engine import Alert, SignalDirection, SignalStrength


# ============================================================
# EMAIL HTML
# ============================================================

def format_email_html(alert: Alert) -> str:
    """
    Email HTML con el análisis completo en lenguaje del libro.
    Compatible con estructura de Alert v4.
    """
    if alert.direction == SignalDirection.CALL:
        accent = "#1a6b3c"
        bg_accent = "rgba(26,107,60,0.08)"
    elif alert.direction == SignalDirection.PUT:
        accent = "#c8401a"
        bg_accent = "rgba(200,64,26,0.08)"
    else:
        accent = "#b8860b"
        bg_accent = "rgba(184,134,11,0.08)"

    # Tendencia 1H
    trend_map = {
        "alcista_fuerte":  "ALCISTA FUERTE (20 > 40 > 100 > 200)",
        "alcista_parcial": "ALCISTA PARCIAL (mayoría alcista)",
        "bajista_fuerte":  "BAJISTA FUERTE (20 < 40 < 100 < 200)",
        "bajista_parcial": "BAJISTA PARCIAL (mayoría bajista)",
        "lateral":         "LATERAL (MAs entrelazadas)"
    }
    trend_1h = trend_map.get(alert.ma.trend_1h, alert.ma.trend_1h)
    trend_daily = trend_map.get(alert.ma.daily_trend, alert.ma.daily_trend)

    # BB 15min status
    if alert.bb.price_above_upper_15m:
        bb_status = f"🔥 Precio SALIÓ de banda superior — percentil {alert.bb.bandwidth_pct_15m:.0f}%"
    elif alert.bb.price_below_lower_15m:
        bb_status = f"🔥 Precio SALIÓ de banda inferior — percentil {alert.bb.bandwidth_pct_15m:.0f}%"
    elif alert.bb.price_near_upper_15m:
        bb_status = f"📡 Precio acercándose a banda superior — percentil {alert.bb.bandwidth_pct_15m:.0f}%"
    elif alert.bb.price_near_lower_15m:
        bb_status = f"📡 Precio acercándose a banda inferior — percentil {alert.bb.bandwidth_pct_15m:.0f}%"
    elif alert.bb.is_squeeze_15m:
        bb_status = f"⚡ SQUEEZE — Explosión inminente"
    elif alert.bb.is_expanding_15m:
        bb_status = f"↗ Expandiendo — percentil {alert.bb.bandwidth_pct_15m:.0f}%"
    else:
        bb_status = f"Normal — percentil {alert.bb.bandwidth_pct_15m:.0f}%"

    # Canal lateral
    canal_txt = f"Sí — {alert.ma.lateral_days_1h} días" if alert.ma.is_lateral_1h else "No detectado"

    # Soporte / Resistencia
    sr_txt = ""
    if alert.ma.bouncing_on:
        rol = "PISO" if alert.ma.bounce_dir == "up" else "TECHO"
        sr_txt = f"""
        <tr style="border-bottom:1px solid #eee;">
            <td style="padding:8px 12px;color:#666;font-size:13px;">Rebote en MA</td>
            <td style="padding:8px 12px;font-size:13px;font-weight:600;">
                {alert.ma.bouncing_on} como {rol}
            </td>
        </tr>"""

    # Puntos ciegos del Diario
    blind_html = ""
    if alert.ma.daily_blind_spots:
        items = "<br>".join([f'⚠️ {b}' for b in alert.ma.daily_blind_spots])
        blind_html = f"""
        <tr style="border-bottom:1px solid #eee;">
            <td style="padding:8px 12px;color:#b8860b;font-size:13px;">Puntos Ciegos Diario</td>
            <td style="padding:8px 12px;font-size:12px;color:#b8860b;font-weight:600;">{items}</td>
        </tr>"""

    # Eventos externos
    if alert.external_events:
        ev_html = "<br>".join([
            f'<span style="color:#b8860b;">{e["warning"]}</span>'
            for e in alert.external_events
        ])
    else:
        ev_html = '<span style="color:#1a6b3c;">Sin eventos macro — señal limpia</span>'

    # Soporte y resistencia 1H
    sup_res = []
    if alert.ma.nearest_support:
        sup_res.append(f"Soporte: {alert.ma.nearest_support}")
    if alert.ma.nearest_resistance:
        sup_res.append(f"Resistencia: {alert.ma.nearest_resistance}")
    sup_res_txt = " | ".join(sup_res) if sup_res else "Sin niveles cercanos"

    html = f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f5f2eb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<div style="max-width:600px;margin:0 auto;padding:24px;">

  <!-- HEADER -->
  <div style="background:#0d1117;color:white;padding:20px 24px;border-bottom:4px solid {accent};">
    <div style="font-size:10px;letter-spacing:2px;opacity:0.5;margin-bottom:8px;">SAAI v4 — SMART ALERT AI SYSTEM</div>
    <div style="font-size:32px;font-weight:800;letter-spacing:-1px;">{alert.ticker}</div>
    <div style="font-size:12px;opacity:0.6;margin-top:4px;">{alert.timestamp}</div>
  </div>

  <!-- ESTRATEGIA -->
  <div style="background:{bg_accent};border-left:4px solid {accent};padding:16px 20px;margin-top:2px;">
    <div style="font-size:10px;letter-spacing:1.5px;color:{accent};margin-bottom:4px;text-transform:uppercase;">Estrategia Identificada</div>
    <div style="font-size:17px;font-weight:700;color:#1a1a18;margin-bottom:8px;">{alert.strategy.value}</div>
    <span style="background:{accent};color:white;padding:4px 12px;font-size:11px;font-weight:700;letter-spacing:1px;">
      {alert.direction.value} {alert.strength.value}
    </span>
    <span style="margin-left:8px;font-size:12px;color:{accent};font-weight:600;">Score: {alert.score}/100</span>
  </div>

  <!-- ANÁLISIS PANORAMA COMPLETO -->
  <div style="background:white;padding:20px 24px;margin-top:2px;border:1px solid #e5e0d5;">
    <div style="font-size:10px;letter-spacing:1.5px;color:#999;margin-bottom:16px;text-transform:uppercase;">Panorama Completo — 3 Temporalidades</div>

    <table style="width:100%;border-collapse:collapse;">
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:8px 12px;color:#666;font-size:13px;">Precio Actual</td>
        <td style="padding:8px 12px;font-size:13px;font-weight:600;">${alert.price}</td>
      </tr>

      <!-- MAs 1H — DECISIÓN -->
      <tr style="border-bottom:1px solid #eee;background:#f8f9ff;">
        <td style="padding:8px 12px;color:#1a3a6b;font-size:13px;font-weight:600;">MAs 1H (DECISIÓN)</td>
        <td style="padding:8px 12px;font-size:13px;font-weight:700;color:#1a3a6b;">{trend_1h}</td>
      </tr>
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:8px 12px;color:#666;font-size:13px;">MA 20 / 40 / 100 / 200</td>
        <td style="padding:8px 12px;font-size:12px;">
          ${alert.ma.ma20_1h} / ${alert.ma.ma40_1h} / ${alert.ma.ma100_1h} / ${alert.ma.ma200_1h}
        </td>
      </tr>
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:8px 12px;color:#666;font-size:13px;">Canal Lateral 1H</td>
        <td style="padding:8px 12px;font-size:13px;">{canal_txt}</td>
      </tr>
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:8px 12px;color:#666;font-size:13px;">Soporte / Resistencia 1H</td>
        <td style="padding:8px 12px;font-size:12px;">{sup_res_txt}</td>
      </tr>
      {sr_txt}

      <!-- BB 15min — ENTRADA -->
      <tr style="border-bottom:1px solid #eee;background:#f8fff8;">
        <td style="padding:8px 12px;color:#1a6b3c;font-size:13px;font-weight:600;">BB 15min (ENTRADA)</td>
        <td style="padding:8px 12px;font-size:13px;font-weight:700;color:#1a6b3c;">{bb_status}</td>
      </tr>
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:8px 12px;color:#666;font-size:13px;">BB Superior / Inferior</td>
        <td style="padding:8px 12px;font-size:12px;">${alert.bb.upper_15m} / ${alert.bb.lower_15m}</td>
      </tr>
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:8px 12px;color:#666;font-size:13px;">Vela 15min</td>
        <td style="padding:8px 12px;font-size:12px;">{alert.bb.candle_type.replace("_"," ").title()}</td>
      </tr>

      <!-- DIARIO — CONTEXTO -->
      <tr style="border-bottom:1px solid #eee;background:#fffdf5;">
        <td style="padding:8px 12px;color:#b8860b;font-size:13px;font-weight:600;">Diario (CONTEXTO)</td>
        <td style="padding:8px 12px;font-size:13px;color:#b8860b;">{trend_daily}</td>
      </tr>
      {blind_html}

      <!-- EVENTOS -->
      <tr>
        <td style="padding:8px 12px;color:#666;font-size:13px;">Eventos Macro</td>
        <td style="padding:8px 12px;font-size:12px;">{ev_html}</td>
      </tr>
    </table>
  </div>

  <!-- EXPLICACIÓN DEL LIBRO -->
  <div style="background:#faf8f3;padding:20px 24px;margin-top:2px;border:1px solid #e5e0d5;">
    <div style="font-size:10px;letter-spacing:1.5px;color:#999;margin-bottom:12px;text-transform:uppercase;">📖 Explicación — Metodología Yoel Sardiñas</div>
    <div style="font-size:13px;line-height:1.9;color:#333;white-space:pre-line;">{alert.explanation}</div>
  </div>

  <!-- RECOMENDACIÓN -->
  <div style="background:{accent};color:white;padding:16px 24px;margin-top:2px;">
    <div style="font-size:10px;letter-spacing:1.5px;opacity:0.7;margin-bottom:6px;text-transform:uppercase;">Recomendación</div>
    <div style="font-size:15px;font-weight:700;line-height:1.7;">{alert.recommendation}</div>
  </div>

  <!-- FOOTER -->
  <div style="padding:20px 24px;font-size:10px;color:#999;text-align:center;line-height:1.9;">
    SAAI v4 — Smart Alert AI System<br>
    Basado en "Un Millón al Año No Hace Daño" — Yoel Sardiñas<br>
    MAs → Decisión en 1H · BB → Entrada en 15min · Diario → Puntos Ciegos<br><br>
    ⚠️ Herramienta de análisis técnico. No garantiza resultados.<br>
    La decisión final siempre es del trader. Confirma en TC2000 antes de entrar.
  </div>

</div>
</body>
</html>"""

    return html


# ============================================================
# EMAIL TEXTO PLANO (fallback)
# ============================================================

def format_sms_text(alert: Alert) -> str:
    """Versión texto plano de la alerta para fallback."""
    emoji = "🟢" if alert.direction == SignalDirection.CALL else "🔴" if alert.direction == SignalDirection.PUT else "⚡"
    strength = "FUERTE" if alert.strength == SignalStrength.FUERTE else "MODERADO"

    txt = (
        f"{emoji} SAAI v4 — {alert.ticker}\n"
        f"{alert.timestamp}\n\n"
        f"📖 {alert.strategy.value}\n"
        f"🎯 {alert.direction.value} {strength} | Score: {alert.score}/100\n\n"
        f"MAs 1H (DECISIÓN): {alert.ma.trend_1h}\n"
        f"BB 15min (ENTRADA): percentil {alert.bb.bandwidth_pct_15m:.0f}%\n"
        f"Diario (CONTEXTO): {alert.ma.daily_trend}\n"
        f"Precio: ${alert.price}\n"
    )

    if alert.ma.bouncing_on:
        rol = "PISO" if alert.ma.bounce_dir == "up" else "TECHO"
        txt += f"Rebote: {alert.ma.bouncing_on} como {rol}\n"

    if alert.ma.daily_warning:
        txt += f"\n{alert.ma.daily_warning}\n"

    if alert.warning:
        txt += f"\n{alert.warning}\n"

    txt += f"\n{alert.recommendation}"
    return txt


# ============================================================
# ENVÍO DE EMAIL — MÚLTIPLES DESTINATARIOS
# ============================================================

def send_email(alert: Alert) -> bool:
    """
    Envía alerta por Email usando Gmail SMTP.
    Soporta múltiples emails en EMAIL_TO separados por coma.
    Ejemplo: EMAIL_TO=email1@gmail.com,email2@gmail.com
    """
    try:
        gmail_user     = os.environ.get("GMAIL_USER")
        gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
        email_to_raw   = os.environ.get("EMAIL_TO", "")

        if not all([gmail_user, gmail_password, email_to_raw]):
            print("[Email] ⚠️ Variables de Gmail no configuradas")
            return False

        # Soporta múltiples emails separados por coma
        recipients = [e.strip() for e in email_to_raw.split(",") if e.strip()]

        if not recipients:
            print("[Email] ⚠️ No hay destinatarios configurados")
            return False

        # Construir email
        msg = MIMEMultipart("alternative")

        emoji = "🟢" if alert.direction == SignalDirection.CALL else "🔴" if alert.direction == SignalDirection.PUT else "⚡"
        msg["Subject"] = (
            f"{emoji} SAAI: {alert.ticker} — "
            f"{alert.direction.value} {alert.strength.value} — "
            f"{alert.strategy.value}"
        )
        msg["From"] = gmail_user
        msg["To"]   = ", ".join(recipients)

        # Adjuntar versión texto y HTML
        msg.attach(MIMEText(format_sms_text(alert), "plain"))
        msg.attach(MIMEText(format_email_html(alert), "html"))

        # Enviar a todos los destinatarios
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, recipients, msg.as_string())

        print(f"[Email] ✅ Enviado a: {', '.join(recipients)}")
        return True

    except Exception as e:
        print(f"[Email] ❌ Error: {e}")
        return False


# ============================================================
# ENVÍO DE SMS — TWILIO (OPCIONAL)
# ============================================================

def send_sms(alert: Alert) -> bool:
    """
    Envía alerta por SMS usando Twilio.
    Si no está configurado, se salta sin error.
    """
    try:
        from twilio.rest import Client

        sid          = os.environ.get("TWILIO_SID")
        token        = os.environ.get("TWILIO_TOKEN")
        from_number  = os.environ.get("TWILIO_FROM")
        to_number    = os.environ.get("TWILIO_TO")

        # Si son placeholders, no enviar
        if not all([sid, token, from_number, to_number]):
            return False
        if "placeholder" in str(sid).lower():
            return False

        client = Client(sid, token)
        body   = format_sms_text(alert)

        message = client.messages.create(
            body=body,
            from_=from_number,
            to=to_number
        )

        print(f"[SMS] ✅ Enviado — SID: {message.sid}")
        return True

    except Exception as e:
        if "placeholder" not in str(e).lower():
            print(f"[SMS] ❌ Error: {e}")
        return False


# ============================================================
# ENVIAR TODOS LOS CANALES
# ============================================================

def send_alert(alert: Alert) -> dict:
    """Envía la alerta por todos los canales configurados."""
    results = {
        "email": send_email(alert),
        "sms":   send_sms(alert)
    }
    print(
        f"[Notificaciones] "
        f"Email: {'✅' if results['email'] else '❌'} | "
        f"SMS: {'✅' if results['sms'] else '⏭️ (no configurado)'}"
    )
    return results
