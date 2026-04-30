"""
SAAI v5.3 — Punto de Entrada Principal
Basado en "Un Millón al Año No Hace Daño" — Yoel Sardiñas

Estrategias: E1 Canal Alza | E2 Canal Baja | E3 Saltos (apertura)
Volatilidad obligatoria: ALTA para E1/E2 | MEDIA+ para E3
"""

import json
import os
from datetime import datetime
from pathlib import Path
import pytz

from analysis_engine import run_analysis, SignalStrength
from notifications import send_alert

ALERT_LOG = Path("alert_history.json")


def load_alert_history() -> dict:
    et    = pytz.timezone('US/Eastern')
    today = datetime.now(et).strftime("%Y-%m-%d")
    if ALERT_LOG.exists():
        with open(ALERT_LOG, "r") as f:
            history = json.load(f)
        if history.get("date") == today:
            return history
    return {"date": today, "alerts": []}


def save_alert_history(history: dict):
    with open(ALERT_LOG, "w") as f:
        json.dump(history, f, indent=2)


def is_duplicate(alert, history: dict) -> bool:
    """Evita enviar la misma alerta dos veces en 30 minutos."""
    key = f"{alert.ticker}_{alert.strategy.value}_{alert.direction.value}"
    et  = pytz.timezone('US/Eastern')
    now = datetime.now(et)

    for sent in history.get("alerts", []):
        if sent.get("key") == key:
            sent_time = datetime.fromisoformat(sent["timestamp"]).replace(tzinfo=et)
            diff      = now - sent_time
            if diff.total_seconds() < 1800:  # 30 minutos
                return True
    return False


def is_market_hours() -> bool:
    et  = pytz.timezone('US/Eastern')
    now = datetime.now(et)

    if now.weekday() >= 5:
        print("[SAAI] Fin de semana — mercado cerrado")
        return False

    market_open  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0,  second=0, microsecond=0)

    if now < market_open or now > market_close:
        print(f"[SAAI] Fuera de horario de mercado — {now.strftime('%I:%M %p ET')}")
        return False

    return True


def main():
    print("\n" + "=" * 65)
    print("  SAAI v5.3 — Smart Alert AI System")
    print("  Un Millón al Año No Hace Daño — Yoel Sardiñas")
    print("  E1: Canal Alza | E2: Canal Baja | E3: Saltos Apertura")
    print("=" * 65)

    if not is_market_hours():
        if os.environ.get("SAAI_TEST_MODE") == "true":
            print("[SAAI] Modo de prueba — ejecutando fuera de horario")
        else:
            print("[SAAI] Terminando — fuera de horario de mercado")
            return

    # Tickers: desde variable de entorno o lista completa del libro
    env_tickers = os.environ.get("SAAI_TICKERS", "")
    tickers = [t.strip() for t in env_tickers.split(",")] if env_tickers else None

    alerts = run_analysis(tickers)

    if not alerts:
        print("\n[SAAI] Sin señales — condiciones por debajo del umbral")
        return

    history   = load_alert_history()
    sent_count = 0

    for alert in alerts:
        # Nunca enviar señales débiles
        if alert.strength == SignalStrength.DEBIL:
            continue

        if is_duplicate(alert, history):
            print(f"[{alert.ticker}] Alerta duplicada — ya enviada recientemente")
            continue

        print(f"\n[{alert.ticker}] Enviando alerta...")
        print(f"  {alert.strategy.value}")
        print(f"  {alert.direction.value} {alert.strength.value} | Score: {alert.score}")
        print(f"  Volatilidad: {alert.bb.volatility_level} ({alert.bb.bandwidth_pct_15m:.0f}%)")

        results = send_alert(alert)

        et  = pytz.timezone('US/Eastern')
        now = datetime.now(et)

        history["alerts"].append({
            "key":        f"{alert.ticker}_{alert.strategy.value}_{alert.direction.value}",
            "timestamp":  now.isoformat(),
            "ticker":     alert.ticker,
            "categoria":  alert.categoria,
            "strategy":   alert.strategy.value,
            "direction":  alert.direction.value,
            "strength":   alert.strength.value,
            "score":      alert.score,
            "volatility": alert.bb.volatility_level,
            "email_sent": results["email"],
        })
        sent_count += 1

    save_alert_history(history)

    print(f"\n{'=' * 65}")
    print(f"  Resumen: {len(alerts)} señales | {sent_count} alertas enviadas")
    print(f"{'=' * 65}\n")


if __name__ == "__main__":
    main()
