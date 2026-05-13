“””
SAAI v6.1 – Punto de Entrada Principal
E4 – Saliendo de Bollinger Bands
“””

import json
import os
from datetime import datetime
from pathlib import Path
import pytz

from analysis_engine import run_analysis, SignalStrength
from notifications import send_alert

ALERT_LOG = Path(“alert_history.json”)

def load_alert_history():
et = pytz.timezone(‘US/Eastern’)
today = datetime.now(et).strftime(”%Y-%m-%d”)
if ALERT_LOG.exists():
with open(ALERT_LOG, “r”) as f:
history = json.load(f)
if history.get(“date”) == today:
return history
return {“date”: today, “alerts”: []}

def save_alert_history(history):
with open(ALERT_LOG, “w”) as f:
json.dump(history, f, indent=2)

def is_duplicate(alert, history):
key = f”{alert.ticker}*{alert.strategy.value}*{alert.direction.value}”
et = pytz.timezone(‘US/Eastern’)
now = datetime.now(et)
for sent in history.get(“alerts”, []):
if sent.get(“key”) == key:
sent_time = datetime.fromisoformat(sent[“timestamp”]).replace(tzinfo=et)
if (now - sent_time).total_seconds() < 1800:
return True
return False

def is_market_hours():
et = pytz.timezone(‘US/Eastern’)
now = datetime.now(et)
if now.weekday() >= 5:
print(”[SAAI] Fin de semana – mercado cerrado”)
return False
market_open  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
market_close = now.replace(hour=16, minute=0,  second=0, microsecond=0)
if now < market_open or now > market_close:
print(f”[SAAI] Fuera de horario de mercado – {now.strftime(’%I:%M %p ET’)}”)
return False
return True

def main():
print(”\n” + “=”*65)
print(”  SAAI v6.1 – Smart Alert AI System”)
print(”  E4 – Saliendo de Bollinger Bands”)
print(”  Basado en documento de metodologia personal”)
print(”=”*65)

```
if not is_market_hours():
    if os.environ.get("SAAI_TEST_MODE") == "true":
        print("[SAAI] Modo de prueba -- ejecutando fuera de horario")
    else:
        print("[SAAI] Terminando -- fuera de horario de mercado")
        return

env_tickers = os.environ.get("SAAI_TICKERS", "")
tickers = [t.strip() for t in env_tickers.split(",")] if env_tickers else None

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
    print(f"  {alert.direction.value} {alert.strength.value} | Score: {alert.score}")

    results = send_alert(alert)

    et = pytz.timezone('US/Eastern')
    now = datetime.now(et)

    history["alerts"].append({
        "key":       f"{alert.ticker}_{alert.strategy.value}_{alert.direction.value}",
        "timestamp": now.isoformat(),
        "ticker":    alert.ticker,
        "categoria": alert.categoria,
        "strategy":  alert.strategy.value,
        "direction": alert.direction.value,
        "strength":  alert.strength.value,
        "score":     alert.score,
        "email_sent": results["email"],
    })
    sent_count += 1

save_alert_history(history)

print(f"\n{'='*65}")
print(f"  Resumen: {len(alerts)} senales | {sent_count} alertas enviadas")
print(f"{'='*65}\n")
```

if **name** == “**main**”:
main()
