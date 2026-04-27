"""
SAAI — Main Entry Point
Ejecuta el análisis completo y envía notificaciones.

Este script es ejecutado por GitHub Actions cada 15 minutos
durante el horario de mercado (9:30am — 4:00pm ET, Lun-Vie).

"El enfoque es la gestión de la atención." — Yoel Sardiñas
"""

import json
import os
from datetime import datetime
from pathlib import Path
import pytz

from analysis_engine import run_analysis, SignalStrength
from notifications import send_alert

# Archivo para rastrear alertas enviadas y evitar duplicados
ALERT_LOG = Path("alert_history.json")


def load_alert_history() -> dict:
    """Carga historial de alertas enviadas hoy."""
    if ALERT_LOG.exists():
        with open(ALERT_LOG, "r") as f:
            history = json.load(f)
        # Limpiar historial si es de otro día
        et = pytz.timezone('US/Eastern')
        today = datetime.now(et).strftime("%Y-%m-%d")
        if history.get("date") != today:
            return {"date": today, "alerts": []}
        return history
    return {"date": datetime.now(pytz.timezone('US/Eastern')).strftime("%Y-%m-%d"), "alerts": []}


def save_alert_history(history: dict):
    """Guarda historial de alertas."""
    with open(ALERT_LOG, "w") as f:
        json.dump(history, f, indent=2)


def is_duplicate(alert, history: dict) -> bool:
    """
    Verifica si ya se envió una alerta similar en los últimos 30 minutos.
    Evita spam de alertas repetidas.
    """
    key = f"{alert.ticker}_{alert.strategy.value}_{alert.direction.value}"
    
    for sent in history.get("alerts", []):
        if sent.get("key") == key:
            # Verificar si fue hace menos de 30 minutos
            sent_time = datetime.fromisoformat(sent["timestamp"])
            et = pytz.timezone('US/Eastern')
            now = datetime.now(et)
            
            if (now - sent_time.replace(tzinfo=et)).total_seconds() < 1800:  # 30 min
                return True
    
    return False


def is_market_hours() -> bool:
    """
    Verifica si estamos en horario de mercado.
    NYSE: 9:30 AM — 4:00 PM Eastern, Lunes a Viernes.
    """
    et = pytz.timezone('US/Eastern')
    now = datetime.now(et)
    
    # Verificar día de la semana (0=Lunes, 6=Domingo)
    if now.weekday() >= 5:  # Sábado o Domingo
        print("[SAAI] Fin de semana — mercado cerrado")
        return False
    
    # Verificar hora
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    
    if now < market_open or now > market_close:
        print(f"[SAAI] Fuera de horario de mercado — {now.strftime('%I:%M %p ET')}")
        return False
    
    return True


def main():
    """
    Punto de entrada principal del sistema SAAI.
    
    Flujo:
    1. Verificar horario de mercado
    2. Ejecutar análisis de 6 capas para SPY, QQQ, DIA
    3. Filtrar señales débiles
    4. Verificar duplicados
    5. Enviar alertas por SMS y email
    6. Registrar en historial
    """
    
    print("\n" + "=" * 60)
    print("  🚀 SAAI — Smart Alert AI System")
    print("  📖 Metodología: Un Millón al Año No Hace Daño")
    print("  👤 Yoel Sardiñas")
    print("=" * 60)
    
    # Verificar si estamos en horario de mercado
    # En GitHub Actions esto se maneja con CRON pero verificamos por seguridad
    if not is_market_hours():
        # Si se ejecuta fuera de horario, permite modo de prueba
        if os.environ.get("SAAI_TEST_MODE") == "true":
            print("[SAAI] ⚠️ Modo de prueba — ejecutando fuera de horario")
        else:
            print("[SAAI] Terminando — fuera de horario de mercado")
            return
    
    # Tickers a monitorear
    tickers = os.environ.get("SAAI_TICKERS", "SPY,QQQ,DIA").split(",")
    
    # Ejecutar análisis
    alerts = run_analysis(tickers)
    
    if not alerts:
        print("\n[SAAI] 📊 Sin señales — todas las condiciones están por debajo del umbral")
        print("[SAAI] 💡 Recuerda: 'Si algún elemento no se presenta, se convierte en una apuesta.'")
        return
    
    # Cargar historial para evitar duplicados
    history = load_alert_history()
    
    # Procesar alertas
    sent_count = 0
    for alert in alerts:
        # Solo enviar FUERTE y MODERADO
        if alert.strength == SignalStrength.DEBIL:
            continue
        
        # Verificar si es duplicado
        if is_duplicate(alert, history):
            print(f"[{alert.ticker}] ⏭️ Alerta duplicada — ya enviada recientemente")
            continue
        
        # Enviar notificaciones
        print(f"\n[{alert.ticker}] 📤 Enviando alerta...")
        print(f"  📖 {alert.strategy.value}")
        print(f"  🎯 {alert.direction.value} {alert.strength.value}")
        
        results = send_alert(alert)
        
        # Registrar en historial
        et = pytz.timezone('US/Eastern')
        history["alerts"].append({
            "key": f"{alert.ticker}_{alert.strategy.value}_{alert.direction.value}",
            "timestamp": datetime.now(et).isoformat(),
            "ticker": alert.ticker,
            "strategy": alert.strategy.value,
            "direction": alert.direction.value,
            "strength": alert.strength.value,
            "sms_sent": results["sms"],
            "email_sent": results["email"]
        })
        
        sent_count += 1
    
    # Guardar historial
    save_alert_history(history)
    
    # Resumen final
    print(f"\n{'=' * 60}")
    print(f"  📊 Resumen: {len(alerts)} señales detectadas, {sent_count} alertas enviadas")
    print(f"  📖 'Las inversiones son 80% emociones y 20% conocimiento.'")
    print(f"  💡 El sistema provee el conocimiento — tú controlas las emociones.")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
