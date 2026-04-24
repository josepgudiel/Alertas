"""
SAAI — Sistema de Notificaciones
Envía alertas por SMS (Twilio) y Email (Gmail SMTP)

Cada alerta incluye:
- Ticker y timestamp
- Estrategia del libro identificada
- Análisis completo de las 6 capas
- Recomendación de acción
- Advertencias de eventos externos
"""

import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from analysis_engine import Alert, SignalDirection, SignalStrength


# ============================================================
# SMS FORMATTING
# ============================================================

def format_sms(alert: Alert) -> str:
    """
    Formatea la alerta para SMS — conciso pero completo.
    Máximo ~400 caracteres para que quepa en 2-3 SMS.
    """
    # Emoji según dirección
    emoji = "🟢" if alert.direction == SignalDirection.CALL else "🔴" if alert.direction == SignalDirection.PUT else "⚡"
    
    # Fuerza
    force = "💪FUERTE" if alert.strength == SignalStrength.FUERTE else "📊MODERADO"
    
    # Trend description
    trend = alert.ma_analysis.trend.replace("_", " ").upper()
    
    sms = (
        f"{emoji} SAAI ALERT — {alert.ticker}\n"
        f"{alert.timestamp}\n"
        f"\n"
        f"📖 {alert.strategy.value}\n"
        f"🎯 {alert.direction.value} {force}\n"
        f"\n"
        f"Precio: ${alert.price}\n"
        f"MAs 1H: {trend}\n"
        f"BB 15m: {'Expandiendo' if alert.bb_analysis.is_expanding else 'Squeeze' if alert.bb_analysis.is_squeeze else 'Normal'}\n"
    )
    
    # Soporte/Resistencia si aplica
    if alert.sr_analysis.bouncing_on_ma:
        sms += f"Rebote: {alert.sr_analysis.bouncing_on_ma} ({alert.sr_analysis.ma_acting_as})\n"
    
    # Gap si aplica
    if alert.gap_analysis and alert.gap_analysis.has_gap:
        sms += f"Salto: {alert.gap_analysis.gap_direction.upper()} ${alert.gap_analysis.gap_size}\n"
    
    # Warning
    if alert.warning:
        sms += f"\n{alert.warning}\n"
    
    sms += f"\n{alert.recommendation}"
    
    return sms


# ============================================================
# EMAIL FORMATTING
# ============================================================

def format_email_html(alert: Alert) -> str:
    """
    Formatea la alerta como email HTML completo con todo el análisis.
    Diseño limpio y profesional.
    """
    # Colors
    if alert.direction == SignalDirection.CALL:
        accent = "#1a6b3c"
        bg_accent = "rgba(26, 107, 60, 0.08)"
        label = "CALL"
    elif alert.direction == SignalDirection.PUT:
        accent = "#c8401a"
        bg_accent = "rgba(200, 64, 26, 0.08)"
        label = "PUT"
    else:
        accent = "#b8860b"
        bg_accent = "rgba(184, 134, 11, 0.08)"
        label = "MONITOREAR"
    
    # MA trend readable
    trend_map = {
        "alcista_fuerte": "ALCISTA FUERTE (20 > 40 > 100 > 200)",
        "alcista_parcial": "ALCISTA PARCIAL (mayoría alcista)",
        "bajista_fuerte": "BAJISTA FUERTE (20 < 40 < 100 < 200)",
        "bajista_parcial": "BAJISTA PARCIAL (mayoría bajista)",
        "lateral": "LATERAL (MAs entrelazadas)"
    }
    trend_text = trend_map.get(alert.ma_analysis.trend, alert.ma_analysis.trend)
    
    # Build event warnings HTML
    events_html = ""
    if alert.external_events:
        events_html = "<br>".join([
            f'<span style="color:#b8860b;">{e.warning_message}</span>'
            for e in alert.external_events
        ])
    else:
        events_html = '<span style="color:#1a6b3c;">Sin eventos macro relevantes — señal limpia</span>'
    
    # Gap info
    gap_html = ""
    if alert.gap_analysis and alert.gap_analysis.has_gap:
        gap_dir = "ALCISTA ↑" if alert.gap_analysis.gap_direction == "up" else "BAJISTA ↓"
        gap_html = f"""
        <tr>
            <td style="padding:8px 12px;color:#666;font-size:13px;">Salto Apertura</td>
            <td style="padding:8px 12px;font-size:13px;font-weight:600;">
                {gap_dir} — ${alert.gap_analysis.gap_size} ({alert.gap_analysis.gap_pct}%)
            </td>
        </tr>
        """
    
    # Support/Resistance info
    sr_html = ""
    if alert.sr_analysis.bouncing_on_ma:
        sr_html = f"""
        <tr>
            <td style="padding:8px 12px;color:#666;font-size:13px;">Rebote en MA</td>
            <td style="padding:8px 12px;font-size:13px;font-weight:600;">
                {alert.sr_analysis.bouncing_on_ma} como {alert.sr_analysis.ma_acting_as.upper()}
            </td>
        </tr>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="margin:0;padding:0;background:#f5f2eb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
    <div style="max-width:600px;margin:0 auto;padding:24px;">
        
        <!-- HEADER -->
        <div style="background:#1a1a18;color:white;padding:20px 24px;border-bottom:3px solid {accent};">
            <div style="font-size:11px;letter-spacing:2px;opacity:0.6;margin-bottom:8px;">SAAI — SMART ALERT AI SYSTEM</div>
            <div style="font-size:28px;font-weight:800;letter-spacing:-0.5px;">{alert.ticker}</div>
            <div style="font-size:12px;opacity:0.7;margin-top:4px;">{alert.timestamp}</div>
        </div>
        
        <!-- STRATEGY -->
        <div style="background:{bg_accent};border-left:4px solid {accent};padding:16px 20px;margin-top:2px;">
            <div style="font-size:11px;letter-spacing:1.5px;color:{accent};margin-bottom:4px;">ESTRATEGIA IDENTIFICADA</div>
            <div style="font-size:18px;font-weight:700;color:#1a1a18;">{alert.strategy.value}</div>
            <div style="margin-top:8px;display:inline-block;background:{accent};color:white;padding:4px 12px;font-size:12px;font-weight:600;letter-spacing:1px;">
                {alert.direction.value} {alert.strength.value}
            </div>
        </div>
        
        <!-- ANÁLISIS COMPLETO -->
        <div style="background:white;padding:20px 24px;margin-top:2px;border:1px solid #e5e0d5;">
            <div style="font-size:11px;letter-spacing:1.5px;color:#999;margin-bottom:16px;">ANÁLISIS COMPLETO — 6 CAPAS</div>
            
            <table style="width:100%;border-collapse:collapse;">
                <tr style="border-bottom:1px solid #eee;">
                    <td style="padding:8px 12px;color:#666;font-size:13px;">Precio Actual</td>
                    <td style="padding:8px 12px;font-size:13px;font-weight:600;">${alert.price}</td>
                </tr>
                <tr style="border-bottom:1px solid #eee;">
                    <td style="padding:8px 12px;color:#666;font-size:13px;">Tendencia MAs 1H</td>
                    <td style="padding:8px 12px;font-size:13px;font-weight:600;">{trend_text}</td>
                </tr>
                <tr style="border-bottom:1px solid #eee;">
                    <td style="padding:8px 12px;color:#666;font-size:13px;">MA 20 / 40 / 100 / 200</td>
                    <td style="padding:8px 12px;font-size:13px;">
                        ${alert.ma_analysis.ma20} / ${alert.ma_analysis.ma40} / ${alert.ma_analysis.ma100} / ${alert.ma_analysis.ma200}
                    </td>
                </tr>
                {sr_html}
                <tr style="border-bottom:1px solid #eee;">
                    <td style="padding:8px 12px;color:#666;font-size:13px;">Canal Lateral</td>
                    <td style="padding:8px 12px;font-size:13px;">
                        {'Sí — ' + str(alert.ma_analysis.lateral_days) + ' días' if alert.ma_analysis.is_lateral_channel else 'No detectado'}
                    </td>
                </tr>
                <tr style="border-bottom:1px solid #eee;">
                    <td style="padding:8px 12px;color:#666;font-size:13px;">Bollinger Bands 15min</td>
                    <td style="padding:8px 12px;font-size:13px;font-weight:600;">
                        {'🔥 EXPANDIENDO +' + str(alert.bb_analysis.expansion_pct) + '%' if alert.bb_analysis.is_expanding else '⚡ SQUEEZE' if alert.bb_analysis.is_squeeze else 'Normal'}
                    </td>
                </tr>
                <tr style="border-bottom:1px solid #eee;">
                    <td style="padding:8px 12px;color:#666;font-size:13px;">BB Superior / Inferior</td>
                    <td style="padding:8px 12px;font-size:13px;">
                        ${alert.bb_analysis.upper_band} / ${alert.bb_analysis.lower_band}
                    </td>
                </tr>
                {gap_html}
                <tr>
                    <td style="padding:8px 12px;color:#666;font-size:13px;">Eventos Macro</td>
                    <td style="padding:8px 12px;font-size:13px;">{events_html}</td>
                </tr>
            </table>
        </div>
        
        <!-- EXPLICACIÓN DEL LIBRO -->
        <div style="background:#faf8f3;padding:20px 24px;margin-top:2px;border:1px solid #e5e0d5;">
            <div style="font-size:11px;letter-spacing:1.5px;color:#999;margin-bottom:12px;">📖 EXPLICACIÓN — METODOLOGÍA YOEL SARDIÑAS</div>
            <div style="font-size:13px;line-height:1.8;color:#333;white-space:pre-line;">{alert.explanation}</div>
        </div>
        
        <!-- RECOMENDACIÓN -->
        <div style="background:{accent};color:white;padding:16px 24px;margin-top:2px;">
            <div style="font-size:11px;letter-spacing:1.5px;opacity:0.7;margin-bottom:4px;">RECOMENDACIÓN</div>
            <div style="font-size:15px;font-weight:600;line-height:1.6;">{alert.recommendation}</div>
        </div>
        
        <!-- FOOTER -->
        <div style="padding:16px 24px;font-size:10px;color:#999;text-align:center;line-height:1.8;">
            SAAI — Smart Alert AI System<br>
            Basado en "Un Millón al Año No Hace Daño" — Yoel Sardiñas<br>
            "Si algún elemento no se presenta, ya no es una estrategia, se convierte en una apuesta."<br>
            <br>
            ⚠️ Este sistema es una herramienta de análisis. No garantiza resultados.<br>
            La decisión final siempre es del trader. Confirma en TC2000 antes de entrar.
        </div>
        
    </div>
    </body>
    </html>
    """
    
    return html


# ============================================================
# SEND FUNCTIONS
# ============================================================

def send_sms(alert: Alert) -> bool:
    """
    Envía alerta por SMS usando Twilio.
    Requiere variables de entorno: TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM, TWILIO_TO
    """
    try:
        from twilio.rest import Client
        
        sid = os.environ.get("TWILIO_SID")
        token = os.environ.get("TWILIO_TOKEN")
        from_number = os.environ.get("TWILIO_FROM")
        to_number = os.environ.get("TWILIO_TO")
        
        if not all([sid, token, from_number, to_number]):
            print("[SMS] ⚠️ Variables de Twilio no configuradas")
            return False
        
        client = Client(sid, token)
        body = format_sms(alert)
        
        message = client.messages.create(
            body=body,
            from_=from_number,
            to=to_number
        )
        
        print(f"[SMS] ✅ Enviado a {to_number} — SID: {message.sid}")
        return True
        
    except Exception as e:
        print(f"[SMS] ❌ Error: {e}")
        return False


def send_email(alert: Alert) -> bool:
    """
    Envía alerta por Email usando Gmail SMTP.
    Requiere variables de entorno: GMAIL_USER, GMAIL_APP_PASSWORD, EMAIL_TO
    """
    try:
        gmail_user = os.environ.get("GMAIL_USER")
        gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
        email_to = os.environ.get("EMAIL_TO")
        
        if not all([gmail_user, gmail_password, email_to]):
            print("[Email] ⚠️ Variables de Gmail no configuradas")
            return False
        
        # Build email
        msg = MIMEMultipart("alternative")
        
        emoji = "🟢" if alert.direction == SignalDirection.CALL else "🔴" if alert.direction == SignalDirection.PUT else "⚡"
        msg["Subject"] = f"{emoji} SAAI: {alert.ticker} — {alert.direction.value} {alert.strength.value} — {alert.strategy.value}"
        msg["From"] = gmail_user
        msg["To"] = email_to
        
        # Plain text fallback
        text_body = format_sms(alert)
        
        # HTML body
        html_body = format_email_html(alert)
        
        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))
        
        # Send
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, email_to, msg.as_string())
        
        print(f"[Email] ✅ Enviado a {email_to}")
        return True
        
    except Exception as e:
        print(f"[Email] ❌ Error: {e}")
        return False


def send_alert(alert: Alert) -> dict:
    """
    Envía alerta por todos los canales configurados.
    """
    results = {
        "sms": send_sms(alert),
        "email": send_email(alert)
    }
    
    print(f"\n[Notificaciones] SMS: {'✅' if results['sms'] else '❌'} | Email: {'✅' if results['email'] else '❌'}")
    return results
