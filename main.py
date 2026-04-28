# SAAI v4 - Main Entry Point

import json
import os
from datetime import datetime
from pathlib import Path
import pytz

from analysis_engine import run_analysis, SignalStrength
from notifications import send_alert

ALERT_LOG = Path("alert_history.json")


def load_alert_history():
    if ALERT_LOG.exists():
        with open(ALERT_LOG, "r") as f:
            history = json.load(f)
        et = pytz.timezone('US/Eastern')
        today = datetime.now(et).strftime("%Y-%m-%d")
        if history.get("date") != today:
            return {"date": today, "alerts": []}
        return history
    return {"date": datetime.now(pytz.timezone('US/Eastern')).strftime("%Y-%m-%d"), "alerts": []}


def save_alert_history(history):
    with open(ALERT_LOG, "w") as f:
        json.dump(history, f, indent=2)


def is_duplicate(alert, history):
    key = f"{alert.ticker}_{alert.strategy.value}_{alert.direction.value}"
    for sent in history.get("alerts", []):
        if sent.get("key") == key:
            sent_time = datetime.fromisoformat(sent["timestamp"])
            et = pytz.timezone('US/Eastern')
            now = datetime.now(et)
            diff = now - sent_time.replace(tzinfo=et)
            if diff.total_seconds() < 1800:
                return True
    return False


def is_market_hours():
    et = pytz.timezone('US/Eastern')
    now = datetime.now(et)
    if now.weekday() >= 5:
        print("[SAAI] Fin de semana -- mercado cerrado")
        return False
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    if now < market_open or now > market_close:
        print(f"[SAAI] Fuera de horario de mercado -- {now.strftime('%I:%M %p ET')}")
        return False
    return True


def main():
    print("\n" + "=" * 60)
    print("  SAAI v4 -- Smart Alert AI System")
    print("  Un Millon al Anno No Hace Danno -- Yoel Sardinas")
    print("=" * 60)

    if not is_market_hours():
        if os.environ.get("SAAI_TEST_MODE") == "true":
            print("[SAAI] Modo de prueba -- ejecutando fuera de horario")
        else:
            print("[SAAI] Terminando -- fuera de horario de mercado")
            return

    tickers = os.environ.get("SAAI_TICKERS", "SPY,QQQ,DIA").split(",")
    alerts = run_analysis(tickers)

    if not alerts:
        print("\n[SAAI] Sin senales -- condiciones por debajo del umbral")
        return

    history = load_alert_history()
    sent_count = 0

    for alert in alerts:
        if alert.strength == SignalStrength.DEBIL:
            continue
        if is_duplicate(alert, history):
            print(f"[{alert.ticker}] Alerta duplicada -- ya enviada recientemente")
            continue

        print(f"\n[{alert.ticker}] Enviando alerta...")
        print(f"  {alert.strategy.value}")
        print(f"  {alert.direction.value} {alert.strength.value}")

        results = send_alert(alert)

        et = pytz.timezone('US/Eastern')
        history["alerts"].append({
            "key": f"{alert.ticker}_{alert.strategy.value}_{alert.direction.value}",
            "timestamp": datetime.now(et).isoformat(),
            "ticker": alert.ticker,
            "strategy": alert.strategy.value,
            "direction": alert.direction.value,
            "strength": alert.strength.value,
            "email_sent": results["email"]
        })
        sent_count += 1

    save_alert_history(history)
    print(f"\n{'=' * 60}")
    print(f"  Resumen: {len(alerts)} senales, {sent_count} alertas enviadas")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
