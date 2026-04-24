# 🚀 SAAI — Smart Alert AI System

> Sistema de alertas de trading basado en **"Un Millón al Año No Hace Daño"** de Yoel Sardiñas.

## ¿Qué hace?

SAAI monitorea **SPY, QQQ y DIA** cada 15 minutos durante el horario de mercado y te envía alertas por **SMS** y **email** cuando detecta oportunidades basadas en las 3 estrategias del libro.

### Las 3 Estrategias Detectadas

| # | Estrategia | Acción | Condiciones |
|---|---|---|---|
| 1 | Canal Lateral al Alza | CALL | MAs laterales 10+ días + ruptura alcista + BB confirmando |
| 2 | Canal Lateral a la Baja | PUT | MAs laterales 10+ días + ruptura bajista + BB confirmando |
| 3 | Saltos | CALL/PUT | Gap significativo en apertura + dirección de tendencia |

### Las 6 Capas de Análisis

1. **Tendencia Mayor** — MAs 20, 40, 100, 200 en 1H
2. **Pisos y Techos** — Rebotes en MAs (soporte/resistencia)
3. **Bollinger Bands** — Apertura de volatilidad en 15min
4. **Estrategia del Libro** — Cuál de las 3 se está formando
5. **Eventos Externos** — FOMC, CPI, OpEx, datos macro
6. **Calidad de Señal** — FUERTE, MODERADO, o DÉBIL

> *"Si algún elemento de la estrategia no se está presentando, ya no es una estrategia, se convierte en una apuesta."* — Yoel Sardiñas

---

## ⚡ Setup Rápido (10 minutos)

### 1. Fork este repositorio

Click "Fork" arriba a la derecha de GitHub.

### 2. Configurar Twilio (SMS)

1. Regístrate en [twilio.com](https://www.twilio.com) — trial gratis con $15 créditos
2. Obtén tu Account SID y Auth Token
3. Obtén un número de teléfono de Twilio

### 3. Configurar Gmail (Email)

1. Activa 2FA en tu cuenta de Google
2. Ve a [myaccount.google.com](https://myaccount.google.com) → Security → App Passwords
3. Genera un App Password para "Mail"

### 4. Agregar Secrets en GitHub

Ve a tu repositorio → Settings → Secrets and variables → Actions → New repository secret

Agrega estos secrets:

| Secret | Valor |
|---|---|
| `TWILIO_SID` | Tu Account SID de Twilio |
| `TWILIO_TOKEN` | Tu Auth Token de Twilio |
| `TWILIO_FROM` | Tu número Twilio (+1XXXXXXXXXX) |
| `TWILIO_TO` | Tu celular (+1XXXXXXXXXX) |
| `GMAIL_USER` | tu_email@gmail.com |
| `GMAIL_APP_PASSWORD` | Tu App Password de Gmail |
| `EMAIL_TO` | tu_email@gmail.com |

### 5. Activar GitHub Actions

1. Ve a la pestaña "Actions" en tu repositorio
2. Habilita los workflows
3. El sistema empezará a correr automáticamente en el próximo horario de mercado

### 6. Prueba Manual

Ve a Actions → "SAAI Alert System" → "Run workflow" para probar inmediatamente.

---

## 📱 Ejemplo de Alerta SMS

```
🟢 SAAI ALERT — SPY
2026-04-23 10:23 AM ET

📖 Estrategia 1 — Canal Lateral al Alza
🎯 CALL 💪FUERTE

Precio: $708.50
MAs 1H: ALCISTA FUERTE
BB 15m: Expandiendo
Rebote: MA200 (soporte)

📍 CALL FUERTE — Panorama completo alineado. Confirmar en TC2000.
```

---

## 💰 Costos

| Componente | Costo |
|---|---|
| GitHub Actions | $0 (2,000 min/mes gratis) |
| Yahoo Finance API | $0 |
| Gmail SMTP | $0 |
| Twilio SMS (después del trial) | ~$3-5/mes |
| **Total** | **$0 — $5/mes** |

---

## 📁 Estructura del Proyecto

```
saai/
├── analysis_engine.py    # Motor de análisis — 6 capas
├── notifications.py      # SMS (Twilio) + Email (Gmail)
├── main.py              # Orquestador principal
├── requirements.txt     # Dependencias Python
├── .env.example         # Template de variables
├── .github/
│   └── workflows/
│       └── saai.yml     # GitHub Actions — CRON cada 15min
└── README.md            # Este archivo
```

---

## ⚠️ Disclaimer

Este sistema es una herramienta de análisis técnico. **No garantiza resultados.** Las inversiones en opciones conllevan riesgo de pérdida total del capital invertido.

> *"Las inversiones son 80% emociones y 20% conocimiento."* — Yoel Sardiñas

El sistema provee el conocimiento — tú eres responsable de las emociones y la disciplina.

---

*SAAI — Basado en "Un Millón al Año No Hace Daño" — Yoel Sardiñas*
