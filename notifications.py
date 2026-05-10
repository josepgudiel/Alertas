"""
SAAI v6.0 -- Sistema de Notificaciones
E4 -- Saliendo de Bollinger Bands
Basado en documento de metodologia personal
"""

import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from analysis_engine import Alert, SignalDirection, SignalStrength, StrategyType


def format_email_html(alert: Alert) -> str:
    if alert.direction == SignalDirection.CALL:
        accent = "#1a6b3c"; bg_accent = "rgba(26,107,60,0.08)"; emoji_dir = "CALL"
    elif alert.direction == SignalDirection.PUT:
        accent = "#c8401a"; bg_accent = "rgba(200,64,26,0.08)"; emoji_dir = "PUT"
    else:
        accent = "#b8860b"; bg_accent = "rgba(184,134,11,0.08)"; emoji_dir = "---"

    # Criterios del documento
    criterios = alert.criterios_call if alert.direction == SignalDirection.CALL else alert.criterios_put

    def crit_row(label, key, extra=""):
        val = criterios.get(key, False)
        icon = "OK" if val else "WARN"
        color = "#1a6b3c" if val else "#c8401a"
        return f"""
        <tr style="border-bottom:1px solid #eee;">
          <td style="padding:6px 12px;color:#666;font-size:12px;">{label}</td>
          <td style="padding:6px 12px;font-size:12px;font-weight:600;color:{color};">{icon} {extra}</td>
        </tr>"""

    # 15min criterios
    if alert.direction == SignalDirection.CALL:
        mid_label    = "MA20 inclinada al alza"
        mid_key      = "15m_mid_alcista"
        precio_label = "Precio SOBRE punto medio"
        precio_key   = "15m_precio_sobre_mid"
        fuerza_label = "Fuerza: banda INF abriendo"
        fuerza_key   = "15m_fuerza_call"
        espacio_label= "Espacio al disipador superior"
        espacio_key  = "15m_espacio_call"
        espacio_val  = f"{alert.bb15.espacio_superior_pct:.2f}%"
        trend_1h_key = "1h_tendencia_call"
        esp_1h_key   = "1h_espacio_call"
        mid_1h_key   = "1h_mid_alcista"
        esp_1h_val   = f"{alert.bb1h.espacio_superior_pct:.2f}%"
    else:
        mid_label    = "MA20 inclinada a la baja"
        mid_key      = "15m_mid_bajista"
        precio_label = "Precio BAJO punto medio"
        precio_key   = "15m_precio_bajo_mid"
        fuerza_label = "Fuerza: banda SUP abriendo"
        fuerza_key   = "15m_fuerza_put"
        espacio_label= "Espacio al disipador inferior"
        espacio_key  = "15m_espacio_put"
        espacio_val  = f"{alert.bb15.espacio_inferior_pct:.2f}%"
        trend_1h_key = "1h_tendencia_put"
        esp_1h_key   = "1h_espacio_put"
        mid_1h_key   = "1h_mid_bajista"
        esp_1h_val   = f"{alert.bb1h.espacio_inferior_pct:.2f}%"

    # Eventos macro
    if alert.external_events:
        ev_html = "<br>".join([f'<span style="color:#b8860b;">{e["warning"]}</span>' for e in alert.external_events])
    else:
        ev_html = '<span style="color:#1a6b3c;">Sin eventos macro -- senal limpia</span>'

    # Earnings
    if alert.earnings.get("has_earnings"):
        days = alert.earnings.get("days_away", 0)
        e_color = "#c8401a" if days == 0 else "#b8860b" if days == 1 else "#666"
        earnings_html = f'<span style="color:{e_color};font-weight:700;">{alert.earnings["warning"]}</span>'
    else:
        earnings_html = '<span style="color:#1a6b3c;">Sin earnings proximos -- senal limpia</span>'

    # Agotamiento
    if alert.agotamiento.get("has_agotamiento"):
        signals_list = "".join([f'<li>{s}</li>' for s in alert.agotamiento.get("signals", [])])
        agot_html = f"""
  <div style="background:#fff8f0;border-left:4px solid #b8860b;padding:16px 20px;margin-top:2px;">
    <div style="font-size:11px;color:#b8860b;margin-bottom:8px;text-transform:uppercase;">Senales de Agotamiento</div>
    <ul style="margin:0;padding-left:18px;font-size:12px;color:#555;">{signals_list}</ul>
    <div style="margin-top:8px;font-size:11px;color:#b8860b;font-style:italic;">
      Si tienes posicion abierta, considera protegerla o salir.
    </div>
  </div>"""
    else:
        agot_html = ""

    html = f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f5f2eb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<div style="max-width:620px;margin:0 auto;padding:24px;">

  <div style="background:#0d1117;color:white;padding:22px 24px;border-bottom:4px solid {accent};">
    <div style="font-size:10px;letter-spacing:2px;opacity:0.5;margin-bottom:6px;">SAAI v6.0 -- SMART ALERT AI SYSTEM</div>
    <div style="display:flex;align-items:center;gap:12px;">
      <span style="background:{accent};color:white;padding:4px 10px;font-size:12px;font-weight:800;border-radius:3px;">E4</span>
      <span style="font-size:30px;font-weight:800;letter-spacing:-1px;">{alert.ticker}</span>
      <span style="font-size:13px;opacity:0.5;">[{alert.categoria}]</span>
    </div>
    <div style="font-size:11px;opacity:0.5;margin-top:6px;">{alert.timestamp}</div>
  </div>

  <div style="background:{bg_accent};border-left:4px solid {accent};padding:16px 20px;margin-top:2px;">
    <div style="font-size:10px;letter-spacing:1.5px;color:{accent};margin-bottom:4px;text-transform:uppercase;">Estrategia Identificada</div>
    <div style="font-size:16px;font-weight:700;color:#1a1a18;margin-bottom:10px;">{alert.strategy.value}</div>
    <span style="background:{accent};color:white;padding:5px 14px;font-size:12px;font-weight:700;letter-spacing:1px;">
      {emoji_dir} {alert.strength.value}
    </span>
    <span style="margin-left:10px;font-size:12px;color:{accent};font-weight:600;">Score: {alert.score}/100</span>
  </div>

  <div style="background:white;padding:20px 24px;margin-top:2px;border:1px solid #e5e0d5;">
    <div style="font-size:10px;letter-spacing:1.5px;color:#999;margin-bottom:16px;text-transform:uppercase;">
      Criterios del Documento -- 3 Temporalidades
    </div>

    <div style="font-size:11px;font-weight:700;color:#1a3a6b;padding:6px 12px;background:#f0f4ff;margin-bottom:4px;">
      15MIN -- ENTRADA (obligatorio)
    </div>
    <table style="width:100%;border-collapse:collapse;">
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:6px 12px;color:#666;font-size:12px;">Precio Actual</td>
        <td style="padding:6px 12px;font-size:14px;font-weight:700;">${alert.bb15.precio}</td>
      </tr>
      {crit_row(mid_label, mid_key, f"Pendiente MA20: {alert.bb15.mid_slope_pct:.4f}%")}
      {crit_row("Bandas abiertas (5-10 grados)", "15m_bandas_abiertas", f"{alert.bb15.bandwidth_pct:.0f}% percentil")}
      {crit_row(precio_label, precio_key, f"MA20: ${alert.bb15.mid}")}
      {crit_row(fuerza_label, fuerza_key, "")}
      {crit_row(espacio_label, espacio_key, espacio_val)}
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:6px 12px;color:#666;font-size:12px;">Banda Superior / Inferior</td>
        <td style="padding:6px 12px;font-size:12px;">${alert.bb15.upper} / ${alert.bb15.lower}</td>
      </tr>
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:6px 12px;color:#666;font-size:12px;">RSI 14 (15min)</td>
        <td style="padding:6px 12px;font-size:12px;font-weight:600;">{alert.bb15.rsi}</td>
      </tr>
    </table>

    <div style="font-size:11px;font-weight:700;color:#1a6b3c;padding:6px 12px;background:#f0fff4;margin-top:8px;margin-bottom:4px;">
      1H -- DECISION (obligatorio)
    </div>
    <table style="width:100%;border-collapse:collapse;">
      {crit_row("Tendencia al alza/baja", trend_1h_key, bb1h.tendencia if hasattr(alert, 'bb1h') else "")}
      {crit_row("Espacio al disipador", esp_1h_key, esp_1h_val)}
      {crit_row("MA20 1H inclinada", mid_1h_key, "")}
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:6px 12px;color:#666;font-size:12px;">Volatilidad 1H (bonus)</td>
        <td style="padding:6px 12px;font-size:12px;">{"OK Abierta" if alert.bb1h.volatilidad_abierta else "Normal (no obligatorio)"}</td>
      </tr>
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:6px 12px;color:#666;font-size:12px;">MA 20 / 40 / 100 / 200</td>
        <td style="padding:6px 12px;font-size:12px;">${alert.bb1h.ma20_1h} / ${alert.bb1h.ma40_1h} / ${alert.bb1h.ma100_1h} / ${alert.bb1h.ma200_1h}</td>
      </tr>
    </table>

    <div style="font-size:11px;font-weight:700;color:#b8860b;padding:6px 12px;background:#fffdf0;margin-top:8px;margin-bottom:4px;">
      DIARIO -- CONTEXTO
    </div>
    <table style="width:100%;border-collapse:collapse;">
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:6px 12px;color:#666;font-size:12px;">Tendencia Diaria</td>
        <td style="padding:6px 12px;font-size:12px;font-weight:600;">{alert.bbdiario.tendencia}</td>
      </tr>
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:6px 12px;color:#666;font-size:12px;">Precio vs MA20 Diario</td>
        <td style="padding:6px 12px;font-size:12px;">{"SOBRE punto medio" if alert.bbdiario.precio_sobre_mid else "BAJO punto medio"}</td>
      </tr>
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:6px 12px;color:#666;font-size:12px;">Eventos Macro</td>
        <td style="padding:6px 12px;font-size:12px;">{ev_html}</td>
      </tr>
      <tr>
        <td style="padding:6px 12px;color:#666;font-size:12px;">Earnings</td>
        <td style="padding:6px 12px;font-size:12px;">{earnings_html}</td>
      </tr>
    </table>
  </div>

  {agot_html}

  <div style="background:#faf8f3;padding:20px 24px;margin-top:2px;border:1px solid #e5e0d5;">
    <div style="font-size:10px;letter-spacing:1.5px;color:#999;margin-bottom:12px;text-transform:uppercase;">
      Analisis Detallado -- Documento de Metodologia
    </div>
    <div style="font-size:12px;line-height:2.0;color:#333;white-space:pre-line;">{alert.explanation}</div>
  </div>

  <div style="background:{accent};color:white;padding:18px 24px;margin-top:2px;">
    <div style="font-size:10px;letter-spacing:1.5px;opacity:0.7;margin-bottom:8px;text-transform:uppercase;">Recomendacion</div>
    <div style="font-size:15px;font-weight:700;line-height:1.8;white-space:pre-line;">{alert.recommendation}</div>
  </div>

  <div style="padding:20px 24px;font-size:10px;color:#aaa;text-align:center;line-height:2.0;">
    SAAI v6.0 -- Smart Alert AI System<br>
    E4 -- Movimiento Saliendo de Bollinger Bands<br><br>
    15min: MA20 + Bandas + Precio + Fuerza<br>
    1H: Tendencia + Espacio + MA20<br>
    Diario: Contexto<br><br>
    La decision final siempre es del trader.<br>
    Confirmar en TC2000 antes de entrar.
  </div>

</div>
</body>
</html>"""
    return html


def format_sms_text(alert: Alert) -> str:
    emoji = "CALL" if alert.direction == SignalDirection.CALL else "PUT"
    criterios = alert.criterios_call if alert.direction == SignalDirection.CALL else alert.criterios_put

    if alert.direction == SignalDirection.CALL:
        ok_count = sum([
            criterios.get("15m_mid_alcista", False),
            criterios.get("15m_bandas_abiertas", False),
            criterios.get("15m_precio_sobre_mid", False),
            criterios.get("15m_fuerza_call", False),
            criterios.get("1h_tendencia_call", False),
            criterios.get("1h_espacio_call", False),
        ])
        espacio = alert.bb15.espacio_superior_pct
    else:
        ok_count = sum([
            criterios.get("15m_mid_bajista", False),
            criterios.get("15m_bandas_abiertas", False),
            criterios.get("15m_precio_bajo_mid", False),
            criterios.get("15m_fuerza_put", False),
            criterios.get("1h_tendencia_put", False),
            criterios.get("1h_espacio_put", False),
        ])
        espacio = alert.bb15.espacio_inferior_pct

    txt = (
        f"{emoji} SAAI v6.0 -- {alert.ticker} [{alert.categoria}]\n"
        f"{alert.timestamp}\n\n"
        f"E4 -- Saliendo de Bollinger Bands\n"
        f"{alert.direction.value} {alert.strength.value} | Score: {alert.score}/100\n\n"
        f"Criterios OK: {ok_count}/6\n"
        f"Vol 15min: {alert.bb15.bandwidth_pct:.0f}% ({alert.bb15.volatilidad})\n"
        f"Espacio al disipador: {espacio:.2f}%\n"
        f"RSI: {alert.bb15.rsi}\n"
        f"1H: {alert.bb1h.tendencia}\n"
        f"Diario: {alert.bbdiario.tendencia}\n"
    )

    if alert.warning:
        txt += f"\n{alert.warning}\n"
    txt += f"\n{alert.recommendation}"
    return txt


def send_email(alert: Alert) -> bool:
    try:
        gmail_user     = os.environ.get("GMAIL_USER")
        gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
        email_to_raw   = os.environ.get("EMAIL_TO", "")

        if not all([gmail_user, gmail_password, email_to_raw]):
            print("[Email] Variables de Gmail no configuradas")
            return False

        recipients = [e.strip() for e in email_to_raw.split(",") if e.strip()]
        if not recipients:
            print("[Email] No hay destinatarios configurados")
            return False

        msg = MIMEMultipart("alternative")
        emoji = "CALL" if alert.direction == SignalDirection.CALL else "PUT"
        msg["Subject"] = (
            f"{emoji} SAAI E4: {alert.ticker} [{alert.categoria}] -- "
            f"{alert.direction.value} {alert.strength.value} -- Score:{alert.score}"
        )
        msg["From"] = gmail_user
        msg["To"]   = ", ".join(recipients)
        msg.attach(MIMEText(format_sms_text(alert),  "plain"))
        msg.attach(MIMEText(format_email_html(alert), "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, recipients, msg.as_string())

        print(f"[Email] Enviado a: {', '.join(recipients)}")
        return True
    except Exception as e:
        print(f"[Email] Error: {e}")
        return False


def send_sms(alert: Alert) -> bool:
    try:
        from twilio.rest import Client
        sid = os.environ.get("TWILIO_SID"); token = os.environ.get("TWILIO_TOKEN")
        from_number = os.environ.get("TWILIO_FROM"); to_number = os.environ.get("TWILIO_TO")
        if not all([sid, token, from_number, to_number]): return False
        if "placeholder" in str(sid).lower(): return False
        client = Client(sid, token)
        message = client.messages.create(body=format_sms_text(alert), from_=from_number, to=to_number)
        print(f"[SMS] Enviado -- SID: {message.sid}")
        return True
    except Exception as e:
        if "placeholder" not in str(e).lower(): print(f"[SMS] Error: {e}")
        return False


def send_alert(alert: Alert) -> dict:
    results = {"email": send_email(alert), "sms": send_sms(alert)}
    print(f"[Notificaciones] Email: {'OK' if results['email'] else 'ERROR'} | SMS: {'OK' if results['sms'] else 'SKIP'}")
    return results
