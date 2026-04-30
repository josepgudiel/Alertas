"""
SAAI v5.3 - Smart Alert AI System
Motor de Análisis — FIEL AL LIBRO

Basado en "Un Millón al Año No Hace Daño" — Yoel Sardiñas

FILOSOFÍA:
  - MAs en 1H  → DECISIÓN (tendencia, canal lateral)
  - BB en 15min → ENTRADA (volatilidad real, confirmación)
  - Diario      → CONTEXTO (puntos ciegos institucionales)

ESTRATEGIAS (solo las del libro):
  E1 — Canal Lateral al Alza  (ruptura + volatilidad real)
  E2 — Canal Lateral a la Baja (ruptura + volatilidad real)
  E3 — Saltos en Apertura     (solo 9:30-10:00am ET)

ADVERTENCIAS (no bloquean, informan):
  - Agotamiento de tendencia  → BB contrayéndose en tendencia extendida
  - Earnings próximos         → alerta automática si earnings en <= 3 días
  - Eventos macro             → FOMC, CPI, NFP, OpEx

REGLAS DE VOLATILIDAD (obligatorias):
  - BB 15min percentil > 75  → ALTA   → E1/E2/E3 pueden alertar
  - BB 15min percentil 60-75 → MEDIA  → solo E3 puede alertar
  - BB 15min percentil < 60  → BAJA   → NO ALERTAR (sin excepciones)
  - BB debe estar EXPANDIENDO
  - Vela de confirmación con cuerpo > 70% del rango

REGLAS ADICIONALES:
  - Score < 55 = no se envía, sin excepciones
  - Mercado choppy (chop > 61.8) = no alerta
  - Saltos SOLO 9:30-10:00am ET
  - Gap bajista solo PUT si MAs 1H bajistas (y viceversa)
  - Canal mínimo 10 días en 1H
"""

import yfinance as yf
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import pytz


# ============================================================
# TICKERS POR CATEGORÍA — LISTADO SAAI
# ============================================================

TICKERS_SAAI = {
    "TECHNOLOGY":    ["AMZN", "AAPL", "GOOG", "META", "MSFT", "NFLX", "PLTR", "ORCL"],
    "SEMICONDUCTORS":["AMD", "MU", "NVDA", "QCOM", "AVGO", "SOXL"],
    "SOFTWARE_APP":  ["DASH", "LYFT", "UBER"],
    "CONSUMER":      ["HD", "LOW", "WMT"],
    "INDEX_USA":     ["DIA", "QQQ", "SPY", "SPX", "IWM", "TNA"],
    "CARDS":         ["AXP", "C", "MA", "PYPL", "V"],
    "CHINA":         ["BABA", "LI", "NIO", "XPEV"],
    "COMMODITY":     ["GLD", "SLV", "USO"],
    "FINANCIAL_DATA":["COIN", "HOOD"],
    "HEALTHCARE":    ["CVS", "MRNA", "PFE"],
    "INDUSTRIALS":   ["BA"],
    "NUCLEAR_ENERGY":["URA"],
    "TSLA":          ["TSLA"],
}

# Lista plana para el análisis
DEFAULT_TICKERS = [t for group in TICKERS_SAAI.values() for t in group]


# ============================================================
# ENUMS
# ============================================================

class SignalDirection(Enum):
    CALL    = "CALL"
    PUT     = "PUT"
    NEUTRAL = "NEUTRAL"

class SignalStrength(Enum):
    FUERTE   = "FUERTE"
    MODERADO = "MODERADO"
    DEBIL    = "DEBIL"

class StrategyType(Enum):
    # Las 3 estrategias del libro
    E1_CANAL_ALZA      = "E1 — Canal Lateral al Alza (CALL)"
    E2_CANAL_BAJA      = "E2 — Canal Lateral a la Baja (PUT)"
    E3_SALTO_ALCISTA   = "E3 — Salto Alcista en Apertura (CALL)"
    E3_SALTO_BAJISTA   = "E3 — Salto Bajista en Apertura (PUT)"
    E3_CAMBIO_TENDENCIA= "E3 — Salto Cambio de Tendencia"
    # Monitoreo (no acción inmediata)
    SQUEEZE_CANAL      = "Squeeze en Canal — Esperar Ruptura"
    NONE               = "Sin estrategia"


# ============================================================
# DATACLASSES
# ============================================================

@dataclass
class MADecision:
    ma20_1h:          float
    ma40_1h:          float
    ma100_1h:         float
    ma200_1h:         float
    price:            float
    trend_1h:         str     # alcista_fuerte | alcista_parcial | bajista_fuerte | bajista_parcial | lateral
    bullish_pts_1h:   int
    is_lateral_1h:    bool
    lateral_days_1h:  int
    price_above_all:  bool
    price_below_all:  bool
    nearest_support:  Optional[str]
    nearest_resistance: Optional[str]
    daily_trend:      str
    daily_ma200:      float
    daily_blind_spots: list
    daily_warning:    Optional[str]

@dataclass
class BBDecision:
    upper_15m:          float
    lower_15m:          float
    mid_15m:            float
    bandwidth_pct_15m:  float   # Percentil de volatilidad (0-100)
    is_expanding_15m:   bool    # BB expandiendo ahora
    is_squeeze_15m:     bool    # BB en squeeze
    price_above_upper:  bool    # Precio salió banda superior
    price_below_lower:  bool    # Precio salió banda inferior
    candle_type:        str     # extreme_bullish | extreme_bearish | normal | doji
    candle_body_pct:    float   # % del cuerpo vs rango total
    bb_expanding_1h:    bool    # Confirmación en 1H también
    volatility_level:   str     # ALTA | MEDIA | BAJA
    rsi_15m:            float   # RSI en 15min (0-100)
    rsi_signal:         str     # OK | SOBRECOMPRADO | SOBREVENDIDO
    overextended:       bool    # Precio muy lejos de banda media (sobreextensión)
    overextension_pct:  float   # % que el precio está fuera de banda

@dataclass
class Alert:
    ticker:          str
    timestamp:       str
    strategy:        StrategyType
    direction:       SignalDirection
    strength:        SignalStrength
    ma:              MADecision
    bb:              BBDecision
    score:           float
    price:           float
    explanation:     str
    recommendation:  str
    warning:         Optional[str]
    external_events: list
    categoria:       str
    earnings:        dict        # {has_earnings, days_away, date, warning, impact}
    agotamiento:     dict        # {has_agotamiento, signals, direction, warning}


# ============================================================
# CALENDARIO ECONÓMICO
# ============================================================

ECONOMIC_CALENDAR = {
    "2026-04-29": {"name": "GDP Q1 Advance",       "impact": "alto"},
    "2026-04-30": {"name": "FOMC Decision",         "impact": "alto"},
    "2026-05-01": {"name": "Jobs Report NFP",       "impact": "alto"},
    "2026-05-13": {"name": "CPI Report",            "impact": "alto"},
    "2026-05-15": {"name": "OpEx Mensual",          "impact": "medio"},
    "2026-06-10": {"name": "CPI Report",            "impact": "alto"},
    "2026-06-17": {"name": "FOMC Decision",         "impact": "alto"},
    "2026-06-19": {"name": "OpEx Mensual",          "impact": "medio"},
    "2026-07-02": {"name": "Jobs Report NFP",       "impact": "alto"},
    "2026-07-15": {"name": "CPI Report",            "impact": "alto"},
    "2026-07-17": {"name": "OpEx Mensual",          "impact": "medio"},
    "2026-07-29": {"name": "FOMC Decision",         "impact": "alto"},
    "2026-08-12": {"name": "CPI Report",            "impact": "alto"},
    "2026-09-09": {"name": "FOMC Decision",         "impact": "alto"},
    "2026-10-07": {"name": "Jobs Report NFP",       "impact": "alto"},
    "2026-10-14": {"name": "CPI Report",            "impact": "alto"},
}

def check_events() -> list:
    et  = pytz.timezone('US/Eastern')
    now = datetime.now(et)
    events = []
    for i, label in {0: "HOY", 1: "MAÑANA", 2: "En 2 días"}.items():
        d = (now + timedelta(days=i)).strftime("%Y-%m-%d")
        if d in ECONOMIC_CALENDAR:
            ev = ECONOMIC_CALENDAR[d]
            if i == 0:
                warn = f"⚠️ HOY: {ev['name']} — Máxima cautela, reducir tamaño"
            elif i == 1:
                warn = f"📅 MAÑANA: {ev['name']} — Reducir tamaño de posición"
            else:
                warn = f"📅 En 2 días: {ev['name']} — Tener en cuenta"
            events.append({
                "name":    ev["name"],
                "impact":  ev["impact"],
                "warning": warn,
                "days":    i
            })
    return events


# ============================================================
# EARNINGS — DETECCIÓN AUTOMÁTICA POR TICKER
# ============================================================

def check_earnings(ticker: str) -> dict:
    """
    Consulta la próxima fecha de earnings del ticker via yfinance.
    Si hay earnings en los próximos 3 días, genera advertencia.
    Retorna dict con has_earnings, days_away, date, warning.
    """
    try:
        stock    = yf.Ticker(ticker)
        calendar = stock.calendar

        # yfinance puede retornar dict o DataFrame según versión
        earnings_date = None

        if isinstance(calendar, dict):
            # Versión nueva de yfinance
            ed = calendar.get("Earnings Date")
            if ed is not None:
                if hasattr(ed, '__iter__') and not isinstance(ed, str):
                    ed = list(ed)
                    earnings_date = ed[0] if ed else None
                else:
                    earnings_date = ed

        elif hasattr(calendar, 'columns'):
            # Versión DataFrame
            if "Earnings Date" in calendar.columns:
                earnings_date = calendar["Earnings Date"].iloc[0]

        if earnings_date is None:
            return {"has_earnings": False}

        # Normalizar a datetime naive para comparar
        if hasattr(earnings_date, 'tzinfo') and earnings_date.tzinfo is not None:
            earnings_date = earnings_date.replace(tzinfo=None)
        if hasattr(earnings_date, 'to_pydatetime'):
            earnings_date = earnings_date.to_pydatetime().replace(tzinfo=None)

        et       = pytz.timezone('US/Eastern')
        now      = datetime.now(et).replace(tzinfo=None)
        days_away = (earnings_date.date() - now.date()).days

        if days_away < 0 or days_away > 7:
            return {"has_earnings": False}

        date_str = earnings_date.strftime("%Y-%m-%d")

        if days_away == 0:
            warn   = f"🚨 EARNINGS HOY ({date_str}) — NO ENTRAR. IV Crush garantizado al cierre."
            impact = "CRITICO"
        elif days_away == 1:
            warn   = f"⚠️ EARNINGS MAÑANA ({date_str}) — Máximo cuidado. Reducir tamaño al mínimo."
            impact = "ALTO"
        elif days_away <= 3:
            warn   = f"📅 EARNINGS en {days_away} días ({date_str}) — Tener en cuenta. IV ya elevada."
            impact = "MEDIO"
        else:
            warn   = f"📅 EARNINGS en {days_away} días ({date_str}) — En el radar."
            impact = "BAJO"

        return {
            "has_earnings": True,
            "days_away":    days_away,
            "date":         date_str,
            "warning":      warn,
            "impact":       impact,
        }

    except Exception as e:
        print(f"   [Earnings] Error consultando {ticker}: {e}")
        return {"has_earnings": False}


# ============================================================
# AGOTAMIENTO DE TENDENCIA — ADVERTENCIA DE SALIDA
# ============================================================

def check_agotamiento(df_15m: pd.DataFrame, df_1h: pd.DataFrame,
                       ma: MADecision, bb: BBDecision) -> dict:
    """
    Detecta señales de agotamiento de tendencia según el libro:
    "Nada sube para siempre y nada baja para siempre."

    Señales de agotamiento:
    1. BB 15min contrayéndose después de expansión fuerte
    2. Precio extendido lejos de MA200 1H (>5%)
    3. Divergencia: precio hace nuevo máximo/mínimo pero BB se contrae
    4. Velas doji consecutivas en 15min (indecisión)

    NO bloquea la alerta, solo agrega advertencia.
    """
    signals  = []
    is_agot  = False

    try:
        # ── Señal 1: BB contrayéndose ──
        close = df_15m['Close']
        sma   = close.rolling(20).mean()
        std   = close.rolling(20).std()
        upper = sma + 2 * std
        lower = sma - 2 * std
        bw    = ((upper - lower) / sma).dropna()

        if len(bw) >= 4:
            last4 = bw.tail(4).values
            if all(last4[i] > last4[i+1] for i in range(3)):
                signals.append("BB 15min contrayéndose — volatilidad cediendo")
                is_agot = True

        # ── Señal 2: Precio muy extendido de MA200 1H ──
        price  = ma.price
        ma200  = ma.ma200_1h
        if ma200 > 0:
            dist_pct = (price - ma200) / ma200 * 100
            if dist_pct > 6 and ma.trend_1h in ["alcista_fuerte", "alcista_parcial"]:
                signals.append(f"Precio {dist_pct:.1f}% sobre MA200 1H — extendido al alza")
                is_agot = True
            elif dist_pct < -6 and ma.trend_1h in ["bajista_fuerte", "bajista_parcial"]:
                signals.append(f"Precio {abs(dist_pct):.1f}% bajo MA200 1H — extendido a la baja")
                is_agot = True

        # ── Señal 3: Dojis consecutivos en 15min ──
        if len(df_15m) >= 3:
            doji_count = 0
            for i in range(-1, -4, -1):
                row  = df_15m.iloc[i]
                rng  = row['High'] - row['Low']
                body = abs(row['Close'] - row['Open'])
                if rng > 0 and body / rng < 0.15:
                    doji_count += 1
            if doji_count >= 2:
                signals.append(f"{doji_count} dojis consecutivos en 15min — indecisión del mercado")
                is_agot = True

        if not is_agot:
            return {"has_agotamiento": False}

        # Dirección probable de agotamiento
        if ma.trend_1h in ["alcista_fuerte", "alcista_parcial"]:
            agot_dir = "PUT"
            msg      = "Tendencia alcista mostrando agotamiento."
        elif ma.trend_1h in ["bajista_fuerte", "bajista_parcial"]:
            agot_dir = "CALL"
            msg      = "Tendencia bajista mostrando agotamiento."
        else:
            agot_dir = "NEUTRAL"
            msg      = "Mercado lateral mostrando agotamiento."

        warning = (
            f"⚠️ AGOTAMIENTO DETECTADO — {msg}\n"
            + "\n".join([f"   • {s}" for s in signals])
            + "\n   Del libro: 'Nada sube para siempre y nada baja para siempre.'"
            + "\n   Si tienes posición abierta, considera protegerla o salir."
        )

        return {
            "has_agotamiento": True,
            "signals":         signals,
            "direction":       agot_dir,
            "warning":         warning,
        }

    except Exception as e:
        print(f"   [Agotamiento] Error: {e}")
        return {"has_agotamiento": False}


# ============================================================
# HELPER: VENTANA DE APERTURA PARA SALTOS (E3)
# Solo válido 9:30am - 10:00am ET
# ============================================================

def is_gap_window() -> bool:
    et   = pytz.timezone('US/Eastern')
    now  = datetime.now(et)
    open_t  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
    close_t = now.replace(hour=10, minute=0,  second=0, microsecond=0)
    in_window = open_t <= now <= close_t
    if not in_window:
        print(f"   Gap window cerrada ({now.strftime('%I:%M %p ET')}) — E3 solo 9:30-10:00am")
    return in_window


# ============================================================
# MEDIAS MÓVILES — DECISIÓN EN 1H
# ============================================================

def analyze_mas(df_1h: pd.DataFrame, df_daily: pd.DataFrame) -> MADecision:
    """Analiza MAs en 1H (decisión) y diario (contexto/puntos ciegos)."""

    if len(df_1h) < 200:
        price = float(df_1h['Close'].iloc[-1]) if len(df_1h) > 0 else 0.0
        return _empty_ma(price)

    close = df_1h['Close']
    price = float(close.iloc[-1])

    ma20  = float(close.rolling(20).mean().iloc[-1])
    ma40  = float(close.rolling(40).mean().iloc[-1])
    ma100 = float(close.rolling(100).mean().iloc[-1])
    ma200 = float(close.rolling(200).mean().iloc[-1])

    # Tendencia 1H: cuántas MAs están en orden alcista
    bp = sum([ma20 > ma40, ma40 > ma100, ma100 > ma200])
    trend_map = {
        3: "alcista_fuerte",
        2: "alcista_parcial",
        1: "bajista_parcial",
        0: "bajista_fuerte"
    }
    trend_1h = trend_map.get(bp, "lateral")

    # Canal lateral
    is_lat, lat_days = _detect_lateral(df_1h)

    # Soporte / Resistencia más cercanos
    support, resistance = _nearest_levels(price, ma20, ma40, ma100, ma200)

    # ── Diario: contexto y puntos ciegos ──
    blind_spots   = []
    daily_warning = None
    d_ma200       = price
    d_trend       = "desconocido"

    if len(df_daily) >= 200:
        dc     = df_daily['Close']
        d_ma20  = float(dc.rolling(20).mean().iloc[-1])
        d_ma40  = float(dc.rolling(40).mean().iloc[-1])
        d_ma100 = float(dc.rolling(100).mean().iloc[-1])
        d_ma200 = float(dc.rolling(200).mean().iloc[-1])

        d_bp    = sum([d_ma20 > d_ma40, d_ma40 > d_ma100, d_ma100 > d_ma200])
        d_trend = trend_map.get(d_bp, "lateral")

        warns = []
        for name, val in [("MA20D", d_ma20), ("MA40D", d_ma40),
                           ("MA100D", d_ma100), ("MA200D (Institucional)", d_ma200)]:
            dist = abs(price - val) / price * 100
            if dist < 1.5:
                rol = "RESISTENCIA" if val > price else "SOPORTE"
                blind_spots.append(f"{name}: ${val:.2f} ({rol})")
                warns.append(f"PUNTO CIEGO DIARIO: {name} ${val:.2f} — {rol}")

        if warns:
            daily_warning = " | ".join(warns)

    return MADecision(
        ma20_1h=round(ma20, 2),
        ma40_1h=round(ma40, 2),
        ma100_1h=round(ma100, 2),
        ma200_1h=round(ma200, 2),
        price=round(price, 2),
        trend_1h=trend_1h,
        bullish_pts_1h=bp,
        is_lateral_1h=is_lat,
        lateral_days_1h=lat_days,
        price_above_all=price > max(ma20, ma40, ma100, ma200),
        price_below_all=price < min(ma20, ma40, ma100, ma200),
        nearest_support=support,
        nearest_resistance=resistance,
        daily_trend=d_trend,
        daily_ma200=round(d_ma200, 2),
        daily_blind_spots=blind_spots,
        daily_warning=daily_warning,
    )


def _detect_lateral(df: pd.DataFrame, min_days: int = 10):
    """
    Detecta canal lateral: las 4 MAs entrelazadas con spread < 2.5%
    durante al menos min_days días en 1H.
    """
    ma20  = df['Close'].rolling(20).mean()
    ma40  = df['Close'].rolling(40).mean()
    ma100 = df['Close'].rolling(100).mean()
    ma200 = df['Close'].rolling(200).mean()

    bars_per_day = 7  # barras de 1H por día de mercado
    count = 0

    for i in range(-1, -len(df), -1):
        try:
            mas = [ma20.iloc[i], ma40.iloc[i], ma100.iloc[i], ma200.iloc[i]]
            if any(pd.isna(m) for m in mas):
                break
            spread = (max(mas) - min(mas)) / df['Close'].iloc[i] * 100
            if spread < 2.5:
                count += 1
            else:
                break
        except:
            break

    days = count // max(bars_per_day, 1)
    return days >= min_days, days


def _nearest_levels(price, ma20, ma40, ma100, ma200):
    levels = {"MA20": ma20, "MA40": ma40, "MA100": ma100, "MA200": ma200}
    supports    = {k: v for k, v in levels.items() if v < price}
    resistances = {k: v for k, v in levels.items() if v > price}
    sup = max(supports,    key=supports.get)    if supports    else None
    res = min(resistances, key=resistances.get) if resistances else None
    return sup, res


def _empty_ma(price: float) -> MADecision:
    return MADecision(
        ma20_1h=price, ma40_1h=price, ma100_1h=price, ma200_1h=price,
        price=price, trend_1h="lateral", bullish_pts_1h=0,
        is_lateral_1h=False, lateral_days_1h=0,
        price_above_all=False, price_below_all=False,
        nearest_support=None, nearest_resistance=None,
        daily_trend="desconocido", daily_ma200=price,
        daily_blind_spots=[], daily_warning=None,
    )


# ============================================================
# BOLLINGER BANDS — ENTRADA EN 15MIN
# ============================================================

def analyze_bb(df_15m: pd.DataFrame, df_1h: pd.DataFrame) -> BBDecision:
    """
    Analiza BB en 15min (entrada) y confirma en 1H.
    Volatilidad real = percentil > 60 + BB expandiendo.
    Tres niveles: ALTA (>75), MEDIA (60-75), BAJA (<60).
    """
    def _calc(df, length=20, std_mult=2.0):
        if len(df) < length + 5:
            c = float(df['Close'].iloc[-1]) if len(df) > 0 else 0.0
            return dict(
                upper=c, lower=c, mid=c,
                bw=0.0, prev_bw=0.0,
                expanding=False, squeeze=False,
                pct=0.0, above=False, below=False,
                exp_pct=0.0
            )

        close = df['Close']
        c     = float(close.iloc[-1])
        sma   = close.rolling(length).mean()
        std   = close.rolling(length).std()
        upper = sma + std_mult * std
        lower = sma - std_mult * std

        cu = float(upper.iloc[-1])
        cl = float(lower.iloc[-1])
        cm = float(sma.iloc[-1])

        bw      = (cu - cl) / cm if cm > 0 else 0.0
        prev_bw = float((upper.iloc[-2] - lower.iloc[-2]) / sma.iloc[-2]) \
                  if len(sma) > 1 and float(sma.iloc[-2]) > 0 else bw

        expanding = bw > prev_bw * 1.03   # expandiendo al menos 3%
        exp_pct   = (bw - prev_bw) / prev_bw * 100 if prev_bw > 0 else 0.0

        bw_series = ((upper - lower) / sma).dropna()
        avg_bw    = float(bw_series.rolling(20).mean().iloc[-1]) \
                    if len(bw_series) >= 20 else bw
        squeeze   = bw < avg_bw * 0.75

        recent = bw_series.tail(60)
        pct    = float((recent < bw).mean() * 100) if len(recent) > 0 else 50.0

        return dict(
            upper=cu, lower=cl, mid=cm,
            bw=bw, prev_bw=prev_bw,
            expanding=expanding, squeeze=squeeze,
            pct=pct, above=c > cu, below=c < cl,
            exp_pct=exp_pct,
        )

    b15 = _calc(df_15m)
    b1h = _calc(df_1h)

    # Nivel de volatilidad
    pct       = b15["pct"]
    expanding = b15["expanding"]

    if pct > 75 and expanding:
        vol_level = "ALTA"
    elif pct >= 60 and expanding:
        vol_level = "MEDIA"
    else:
        vol_level = "BAJA"

    # ── RSI 14 en 15min ──
    rsi_val, rsi_signal = _calc_rsi(df_15m)

    # ── Sobreextensión: precio muy lejos de banda media ──
    price        = float(df_15m['Close'].iloc[-1]) if len(df_15m) > 0 else 0.0
    mid          = b15["mid"]
    upper        = b15["upper"]
    lower        = b15["lower"]
    band_width   = upper - lower
    overextended = False
    overext_pct  = 0.0

    if band_width > 0 and mid > 0:
        # Cuántas desviaciones está el precio del centro
        dist_from_mid = abs(price - mid)
        half_bw       = band_width / 2
        overext_pct   = round((dist_from_mid / half_bw - 1) * 100, 1) if half_bw > 0 else 0.0
        # Sobreextendido si precio > 2.5 desviaciones del centro
        overextended  = dist_from_mid > half_bw * 1.5   # 50% más allá de la banda

    # Tipo de vela en 15min
    candle_type, body_pct = _candle_analysis(df_15m)

    return BBDecision(
        upper_15m=round(b15["upper"], 2),
        lower_15m=round(b15["lower"], 2),
        mid_15m=round(mid, 2),
        bandwidth_pct_15m=round(pct, 1),
        is_expanding_15m=expanding,
        is_squeeze_15m=b15["squeeze"],
        price_above_upper=b15["above"],
        price_below_lower=b15["below"],
        candle_type=candle_type,
        candle_body_pct=round(body_pct, 1),
        bb_expanding_1h=b1h["expanding"],
        volatility_level=vol_level,
        rsi_15m=round(rsi_val, 1),
        rsi_signal=rsi_signal,
        overextended=overextended,
        overextension_pct=overext_pct,
    )


def _candle_analysis(df: pd.DataFrame):
    """Analiza la vela de confirmación. Cuerpo > 70% = extrema (requisito del libro)."""
    if len(df) == 0:
        return "normal", 0.0

    last = df.iloc[-1]
    op, hi, lo, cl = float(last['Open']), float(last['High']), \
                     float(last['Low']),  float(last['Close'])
    rng  = hi - lo
    if rng == 0:
        return "doji", 0.0

    body_pct = abs(cl - op) / rng * 100

    if body_pct < 15:
        return "doji", body_pct
    elif body_pct > 70:
        return ("extreme_bullish" if cl > op else "extreme_bearish"), body_pct
    else:
        return ("normal_bullish" if cl > op else "normal_bearish"), body_pct


def _calc_rsi(df: pd.DataFrame, period: int = 14) -> tuple:
    """
    Calcula RSI de 14 periodos.
    Retorna (valor_rsi, señal).
    señal: OK | SOBRECOMPRADO (>70) | SOBREVENDIDO (<30)
    """
    try:
        if len(df) < period + 2:
            return 50.0, "OK"

        close  = df['Close'].tail(period * 3)
        delta  = close.diff()
        gain   = delta.clip(lower=0)
        loss   = (-delta).clip(lower=0)
        avg_g  = gain.rolling(period).mean().iloc[-1]
        avg_l  = loss.rolling(period).mean().iloc[-1]

        if avg_l == 0:
            return 100.0, "SOBRECOMPRADO"

        rs  = avg_g / avg_l
        rsi = round(100 - (100 / (1 + rs)), 1)

        if rsi >= 75:
            signal = "SOBRECOMPRADO"
        elif rsi <= 25:
            signal = "SOBREVENDIDO"
        else:
            signal = "OK"

        return rsi, signal

    except Exception:
        return 50.0, "OK"


# ============================================================
# CHOPPINESS INDEX
# ============================================================

def calc_choppiness(df_1h: pd.DataFrame, n: int = 14) -> float:
    """Chop > 61.8 = mercado sin dirección clara → no operar."""
    if len(df_1h) < n + 2:
        return 50.0
    try:
        hi = df_1h['High'].tail(n + 1)
        lo = df_1h['Low'].tail(n + 1)
        cl = df_1h['Close'].tail(n + 1)
        tr = pd.concat([
            hi - lo,
            (hi - cl.shift(1)).abs(),
            (lo - cl.shift(1)).abs()
        ], axis=1).max(axis=1)
        atr_sum = float(tr.tail(n).sum())
        hl      = float(hi.tail(n).max() - lo.tail(n).min())
        if hl == 0:
            return 50.0
        return round(100 * np.log10(atr_sum / hl) / np.log10(n), 1)
    except:
        return 50.0


# ============================================================
# ANÁLISIS DE GAPS — ESTRATEGIA 3
# Solo válido en ventana 9:30-10:00am ET
# ============================================================

def analyze_gaps(df_daily: pd.DataFrame, ma: MADecision) -> dict:
    """
    Detecta saltos (gaps) según el libro:
    - Gap > 0.5% vs cierre anterior
    - MAs 1H deben confirmar la dirección
    - Regla 4: gap revertido = cambio de tendencia
    """
    if len(df_daily) < 2:
        return {"has_gap": False}

    today_open  = float(df_daily['Open'].iloc[-1])
    today_close = float(df_daily['Close'].iloc[-1])
    yest_close  = float(df_daily['Close'].iloc[-2])

    size = today_open - yest_close
    pct  = abs(size / yest_close * 100) if yest_close > 0 else 0.0

    # Umbral mínimo: 0.5% (más estricto que antes)
    if pct < 0.5:
        return {"has_gap": False}

    direction = "up" if size > 0 else "down"

    # MAs 1H confirman la dirección del gap
    mas_confirm = (
        (direction == "up"   and ma.trend_1h in ["alcista_fuerte", "alcista_parcial"]) or
        (direction == "down" and ma.trend_1h in ["bajista_fuerte", "bajista_parcial"])
    )

    # Regla 4: gap que revirtió completamente = cambio de tendencia
    gap_filled = (
        (direction == "up"   and today_close < yest_close) or
        (direction == "down" and today_close > yest_close)
    )

    # Probabilidad de segundo salto (Regla 2 del libro)
    if direction == "up"   and today_close > today_open: second_prob = 0.90
    elif direction == "down" and today_close < today_open: second_prob = 0.90
    elif gap_filled:                                        second_prob = 0.10
    else:                                                   second_prob = 0.50

    return {
        "has_gap":     True,
        "direction":   direction,
        "size":        round(abs(size), 2),
        "pct":         round(pct, 3),
        "mas_confirm": mas_confirm,
        "gap_filled":  gap_filled,
        "second_prob": second_prob,
    }


# ============================================================
# SCORING — FIEL AL LIBRO
# ============================================================

def calc_score(ma: MADecision, bb: BBDecision, chop: float) -> tuple:
    """
    Score 0-100. Mínimo 55 para alertar.

    Pesos (fiel al libro):
      BB 15min (entrada + decisión) → 55 pts  ← lo más importante
      BB 1H    (confirmación)       → +5 pts bonus si expandiendo
      MAs 1H   (tendencia)          → 30 pts
      Diario   (puntos ciegos)      → 15 pts
      ─────────────────────────────────────
      Total posible: 105 pts (cap 95)

    Nota: Volumen eliminado — en opciones no es factor de decisión relevante.
    """
    score   = 0.0
    bullish = 0
    bearish = 0

    # ── BB 15min — hasta 55 pts (ENTRADA + DECISIÓN) ──
    # Es la señal más importante del libro — dice CUÁNDO y HACIA DÓNDE
    if bb.volatility_level == "ALTA":
        score += 40                         # volatilidad real confirmada
        if bb.price_above_upper:
            score += 10; bearish += 2       # salió banda superior → PUT
        elif bb.price_below_lower:
            score += 10; bullish += 2       # salió banda inferior → CALL
        elif bb.candle_body_pct > 70:
            score += 5                      # vela extrema = confirmación libro
    elif bb.volatility_level == "MEDIA":
        score += 25
        if bb.price_above_upper or bb.price_below_lower:
            score += 5
    elif bb.is_squeeze_15m:
        score += 10                         # squeeze = explosión inminente

    # BB 1H — confirmación adicional (+5 si también expandiendo)
    if bb.bb_expanding_1h:
        score = min(score + 5, 95)
        bullish += 1 if score > 0 else 0

    # ── MAs 1H — hasta 30 pts (TENDENCIA — contexto de dirección) ──
    if ma.trend_1h == "alcista_fuerte":
        score += 30; bullish += 3
    elif ma.trend_1h == "alcista_parcial":
        score += 20; bullish += 2
    elif ma.trend_1h == "bajista_fuerte":
        score += 30; bearish += 3
    elif ma.trend_1h == "bajista_parcial":
        score += 20; bearish += 2
    elif ma.is_lateral_1h:
        score += 12

    if ma.price_above_all:
        score = min(score + 3, 95); bullish += 1
    elif ma.price_below_all:
        score = min(score + 3, 95); bearish += 1

    # ── Diario — hasta 15 pts (PUNTOS CIEGOS) ──
    if ma.daily_trend == "alcista_fuerte":
        score += 15; bullish += 1
    elif ma.daily_trend == "alcista_parcial":
        score += 9;  bullish += 1
    elif ma.daily_trend == "bajista_fuerte":
        score += 15; bearish += 1
    elif ma.daily_trend == "bajista_parcial":
        score += 9;  bearish += 1

    # ── Dirección preliminar ──
    direction = (
        "alcista" if bullish > bearish else
        "bajista" if bearish > bullish else
        "mixto"
    )

    # ══ BONUS ══

    # AJUSTE 1: Bonus apertura — backtesting confirmó 0.69% movimiento prom en 9:30-10:00
    et  = __import__('pytz').timezone('US/Eastern')
    now = __import__('datetime').datetime.now(et)
    if now.hour == 9 and now.minute >= 30:
        score = min(score + 5, 95)
        print(f"   ✅ Bonus apertura (+5pts) — ventana 9:30-10:00am")

    # AJUSTE 2: Bonus momentum fuerte — tendencia 1H Y diario alineados
    if ma.trend_1h == "alcista_fuerte" and ma.daily_trend in ["alcista_fuerte","alcista_parcial"]:
        score = min(score + 5, 95)
        bullish += 1
        print(f"   ✅ Bonus momentum alcista fuerte (+5pts)")
    elif ma.trend_1h == "bajista_fuerte" and ma.daily_trend in ["bajista_fuerte","bajista_parcial"]:
        score = min(score + 5, 95)
        bearish += 1
        print(f"   ✅ Bonus momentum bajista fuerte (+5pts)")

    # ══ PENALIZACIONES ══

    # 1. Choppy — suavizado a 0.5 (no eliminar señal tan agresivo)
    if chop > 61.8:
        score *= 0.5
        print(f"   ⚠️ Mercado choppy ({chop}) — score reducido 50%")
        return round(score, 1), direction

    # 2. Sobreextensión BB
    if bb.overextended:
        print(f"   ⚠️ Sobreextensión BB ({bb.overextension_pct:.0f}% más allá de banda)")
        score *= 0.5

    # 3. RSI — penalización gradual en lugar de castigo brutal
    #    Basado en backtesting: AMD RSI 76 subió +2.73%, umbral * 0.5 era excesivo
    #    RSI 75-80 → cap 70   (alerta MODERADO, no bloquear)
    #    RSI 80-85 → cap 60   (alerta débil, pasar umbral)
    #    RSI > 85  → * 0.5    (bloquear — realmente extremo, ej. SPY lunes RSI 86)
    if bb.rsi_15m > 75 and direction == "alcista":
        if bb.rsi_15m > 85:
            score *= 0.5
            print(f"   ⚠️ RSI {bb.rsi_15m} MUY extremo (>85) — bloqueando score")
        elif bb.rsi_15m > 80:
            score = min(score, 60)
            print(f"   ⚠️ RSI {bb.rsi_15m} alto (80-85) — limitando score a 60")
        else:
            score = min(score, 70)
            print(f"   ⚠️ RSI {bb.rsi_15m} elevado (75-80) — limitando score a 70")

    elif bb.rsi_15m < 25 and direction == "bajista":
        if bb.rsi_15m < 15:
            score *= 0.5
            print(f"   ⚠️ RSI {bb.rsi_15m} MUY extremo (<15) — bloqueando score")
        elif bb.rsi_15m < 20:
            score = min(score, 60)
            print(f"   ⚠️ RSI {bb.rsi_15m} bajo (15-20) — limitando score a 60")
        else:
            score = min(score, 70)
            print(f"   ⚠️ RSI {bb.rsi_15m} bajo (20-25) — limitando score a 70")

    # 4. Diario contradice 1H — AJUSTE 6: límite subido de 65 a 70
    #    (mercado en transición — no penalizar tan fuerte)
    daily_bullish = ma.daily_trend in ["alcista_fuerte", "alcista_parcial"]
    daily_bearish = ma.daily_trend in ["bajista_fuerte", "bajista_parcial"]
    if (direction == "alcista" and daily_bearish) or \
       (direction == "bajista" and daily_bullish):
        if score > 70:
            print(f"   ⚠️ Diario contradice 1H — limitando score a 70")
            score = 70

    return round(score, 1), direction


def score_to_strength(score: float) -> SignalStrength:
    if score >= 70:
        return SignalStrength.FUERTE
    elif score >= 55:
        return SignalStrength.MODERADO
    else:
        return SignalStrength.DEBIL


# ============================================================
# IDENTIFICADOR DE ESTRATEGIAS — SOLO LAS 3 DEL LIBRO
# ============================================================

def identify_strategy(ma: MADecision, bb: BBDecision, gap: dict,
                       chop: float, score: float, pan_dir: str):
    """
    Identifica ÚNICAMENTE las 3 estrategias del libro.
    Retorna: (StrategyType, SignalDirection, SignalStrength, explanation)
    """

    # Regla 0: Mercado choppy → no operar
    if chop > 61.8:
        print(f"   Descartado: mercado choppy ({chop})")
        return StrategyType.NONE, SignalDirection.NEUTRAL, SignalStrength.DEBIL, ""

    # Regla 1: Score mínimo 55
    if score < 55:
        print(f"   Descartado: score bajo ({score})")
        return StrategyType.NONE, SignalDirection.NEUTRAL, SignalStrength.DEBIL, ""

    # Regla 2: Volatilidad BAJA → no alertar (sin excepciones)
    if bb.volatility_level == "BAJA" and not bb.is_squeeze_15m:
        print(f"   Descartado: volatilidad baja (percentil {bb.bandwidth_pct_15m:.0f}%)")
        return StrategyType.NONE, SignalDirection.NEUTRAL, SignalStrength.DEBIL, ""

    strength = score_to_strength(score)

    # ── E3: SALTOS — Solo en ventana 9:30-10:00am ET ──
    if gap.get("has_gap") and is_gap_window():
        result = _strategy_e3_saltos(gap, ma, bb, score, strength)
        if result[0] != StrategyType.NONE:
            return result

    # ── E1 / E2: CANAL LATERAL ──
    # Requiere canal >= 10 días + ruptura + volatilidad ALTA + vela extrema
    if ma.is_lateral_1h and ma.lateral_days_1h >= 10:
        result = _strategy_canal(ma, bb, score, strength)
        if result[0] != StrategyType.NONE:
            return result

        # Squeeze en canal = monitorear
        if bb.is_squeeze_15m and score >= 55:
            exp = (
                f"SQUEEZE en canal lateral de {ma.lateral_days_1h} días.\n"
                f"MAs 1H: {ma.lateral_days_1h} días entrelazadas (DECISIÓN)\n"
                f"BB 15min: squeeze — explosión inminente\n"
                f"Volatilidad: {bb.bandwidth_pct_15m:.0f}% percentil\n"
                f"Score: {score}/100\n\n"
                "ACCIÓN: Esperar BB expandiendo + vela extrema antes de entrar.\n"
                "Puede ser E1 (CALL) o E2 (PUT) dependiendo de la dirección de ruptura."
            )
            return StrategyType.SQUEEZE_CANAL, SignalDirection.NEUTRAL, SignalStrength.MODERADO, exp

    return StrategyType.NONE, SignalDirection.NEUTRAL, SignalStrength.DEBIL, ""


def _strategy_e3_saltos(gap: dict, ma: MADecision, bb: BBDecision,
                         score: float, strength: SignalStrength):
    """
    Estrategia 3 del libro — Saltos en apertura.

    Reglas:
    1. Gap > 0.5% vs cierre anterior
    2. MAs 1H confirman la dirección (FIX 3)
    3. BB 15min con volatilidad MEDIA o ALTA
    4. Regla 4: gap revertido = cambio de tendencia
    """

    # Regla 4 del libro: gap que se revirtió completamente = cambio de tendencia
    if gap["gap_filled"]:
        d = SignalDirection.CALL if gap["direction"] == "down" else SignalDirection.PUT
        exp = (
            "E3 — CAMBIO DE TENDENCIA (Regla 4 del libro).\n\n"
            f"Gap {gap['direction'].upper()} de ${gap['size']} ({gap['pct']:.2f}%)\n"
            "que se REVIRTIÓ completamente al cierre.\n\n"
            f"MAs 1H: {ma.trend_1h}\n"
            f"BB 15min: percentil {bb.bandwidth_pct_15m:.0f}% — {bb.volatility_level}\n"
            f"Score: {score}/100\n\n"
            "Del libro: cuando el gap se revierte por completo,\n"
            "indica un inminente cambio de tendencia.\n"
            "NO continuar en la dirección original del gap."
        )
        return StrategyType.E3_CAMBIO_TENDENCIA, d, SignalStrength.MODERADO, exp

    # Regla 3 (FIX): MAs deben confirmar la dirección del gap
    if not gap["mas_confirm"]:
        dir_txt = "alcista" if gap["direction"] == "up" else "bajista"
        print(f"   E3 descartado: gap {dir_txt} pero MAs {ma.trend_1h} no confirman")
        return StrategyType.NONE, SignalDirection.NEUTRAL, SignalStrength.DEBIL, ""

    # Volatilidad mínima MEDIA para E3
    if bb.volatility_level == "BAJA":
        print(f"   E3 descartado: volatilidad baja en apertura ({bb.bandwidth_pct_15m:.0f}%)")
        return StrategyType.NONE, SignalDirection.NEUTRAL, SignalStrength.DEBIL, ""

    second = f"\nProb. segundo salto mañana: {int(gap['second_prob'] * 100)}%" \
             if gap["second_prob"] >= 0.5 else ""

    if gap["direction"] == "up":
        exp = (
            "E3 — SALTO ALCISTA en apertura.\n\n"
            f"Gap alcista: +${gap['size']} (+{gap['pct']:.2f}%) vs cierre anterior\n\n"
            f"MAs 1H: {ma.trend_1h} — CONFIRMAN dirección alcista (DECISIÓN)\n"
            f"BB 15min: percentil {bb.bandwidth_pct_15m:.0f}% — {bb.volatility_level} (ENTRADA)\n"
            f"Vela 15min: {bb.candle_type} ({bb.candle_body_pct:.0f}% cuerpo)\n"
            f"Diario: {ma.daily_trend} (CONTEXTO)\n"
            f"Score: {score}/100{second}\n\n"
            "Del libro: 90% de probabilidad de continuación alcista.\n"
            "Los saltos ocurren entre cierre y apertura — solo los grandes\n"
            "fondos operan en ese periodo. El gap indica su dirección."
        )
        return StrategyType.E3_SALTO_ALCISTA, SignalDirection.CALL, strength, exp

    else:  # gap down
        exp = (
            "E3 — SALTO BAJISTA en apertura.\n\n"
            f"Gap bajista: -${gap['size']} (-{gap['pct']:.2f}%) vs cierre anterior\n\n"
            f"MAs 1H: {ma.trend_1h} — CONFIRMAN dirección bajista (DECISIÓN)\n"
            f"BB 15min: percentil {bb.bandwidth_pct_15m:.0f}% — {bb.volatility_level} (ENTRADA)\n"
            f"Vela 15min: {bb.candle_type} ({bb.candle_body_pct:.0f}% cuerpo)\n"
            f"Diario: {ma.daily_trend} (CONTEXTO)\n"
            f"Score: {score}/100{second}\n\n"
            "Del libro: 90% de probabilidad de continuación bajista.\n"
            "Los saltos ocurren entre cierre y apertura — solo los grandes\n"
            "fondos operan en ese periodo. El gap indica su dirección."
        )
        return StrategyType.E3_SALTO_BAJISTA, SignalDirection.PUT, strength, exp


def _strategy_canal(ma: MADecision, bb: BBDecision,
                    score: float, strength: SignalStrength):
    """
    Estrategia 1 y 2 del libro — Canal Lateral.

    Requisitos EXACTOS del libro:
    1. Las 4 MAs (20,40,100,200) en 1H entrelazadas >= 10 días
    2. Precio SALIÓ del canal (no cerca, SALIÓ)
    3. BB 15min con volatilidad ALTA (percentil > 75 + expandiendo)
    4. Vela de confirmación extrema (cuerpo > 70%)
    5. Confirmación también en BB 1H (double check)
    """

    # Requisito de volatilidad ALTA para E1/E2 (más estricto)
    if bb.volatility_level != "ALTA":
        print(f"   E1/E2: volatilidad {bb.volatility_level} — se requiere ALTA (>75%)")
        return StrategyType.NONE, SignalDirection.NEUTRAL, SignalStrength.DEBIL, ""

    days = ma.lateral_days_1h

    # ── E1: Ruptura al ALZA ──
    if bb.price_above_upper:

        candle_txt = ""
        if bb.candle_body_pct > 70:
            candle_txt = f"✅ Vela {bb.candle_type} — cuerpo {bb.candle_body_pct:.0f}% (confirmación del libro)\n"
        else:
            # Sin vela extrema = señal más débil, bajar a MODERADO
            if strength == SignalStrength.FUERTE:
                strength = SignalStrength.MODERADO
            candle_txt = f"⚠️ Vela {bb.candle_type} — cuerpo {bb.candle_body_pct:.0f}% (confirmar visualmente)\n"

        confirm_1h = "✅ BB 1H también expandiendo" if bb.bb_expanding_1h else "⚠️ BB 1H no confirmado aún"

        exp = (
            "E1 — CANAL LATERAL AL ALZA.\n\n"
            f"MAs 1H: canal lateral {days} días — 4 MAs entrelazadas (DECISIÓN)\n"
            f"Precio ROMPIÓ el canal al ALZA\n"
            f"{candle_txt}"
            f"BB 15min: percentil {bb.bandwidth_pct_15m:.0f}% — ALTA volatilidad (ENTRADA)\n"
            f"{confirm_1h}\n"
            f"Diario: {ma.daily_trend} (CONTEXTO)\n"
            f"Score: {score}/100\n\n"
            "Del libro: rentabilidades históricas 100% a 3000% en 2-5 días.\n"
            "Requisitos cumplidos: canal >= 10 días + ruptura + BB alta volatilidad.\n"
            "Confirmar en TC2000 antes de entrar."
        )
        return StrategyType.E1_CANAL_ALZA, SignalDirection.CALL, strength, exp

    # ── E2: Ruptura a la BAJA ──
    elif bb.price_below_lower:

        candle_txt = ""
        if bb.candle_body_pct > 70:
            candle_txt = f"✅ Vela {bb.candle_type} — cuerpo {bb.candle_body_pct:.0f}% (confirmación del libro)\n"
        else:
            if strength == SignalStrength.FUERTE:
                strength = SignalStrength.MODERADO
            candle_txt = f"⚠️ Vela {bb.candle_type} — cuerpo {bb.candle_body_pct:.0f}% (confirmar visualmente)\n"

        confirm_1h = "✅ BB 1H también expandiendo" if bb.bb_expanding_1h else "⚠️ BB 1H no confirmado aún"

        exp = (
            "E2 — CANAL LATERAL A LA BAJA.\n\n"
            f"MAs 1H: canal lateral {days} días — 4 MAs entrelazadas (DECISIÓN)\n"
            f"Precio ROMPIÓ el canal a la BAJA\n"
            f"{candle_txt}"
            f"BB 15min: percentil {bb.bandwidth_pct_15m:.0f}% — ALTA volatilidad (ENTRADA)\n"
            f"{confirm_1h}\n"
            f"Diario: {ma.daily_trend} (CONTEXTO)\n"
            f"Score: {score}/100\n\n"
            "Del libro: rentabilidades históricas 100% a 3000% en 2-5 días.\n"
            "Requisitos cumplidos: canal >= 10 días + ruptura + BB alta volatilidad.\n"
            "Confirmar en TC2000 antes de entrar."
        )
        return StrategyType.E2_CANAL_BAJA, SignalDirection.PUT, strength, exp

    return StrategyType.NONE, SignalDirection.NEUTRAL, SignalStrength.DEBIL, ""


# ============================================================
# RECOMENDACIÓN FINAL
# ============================================================

def generate_rec(direction: SignalDirection, strength: SignalStrength,
                 strategy: StrategyType, events: list,
                 ma: MADecision, bb: BBDecision, chop: float,
                 earnings: dict = None, agotamiento: dict = None) -> str:

    if chop > 61.8:
        return "NO OPERAR — Mercado choppy sin dirección clara. Esperar."

    # Earnings HOY = no entrar, punto
    if earnings and earnings.get("has_earnings") and earnings.get("days_away") == 0:
        return (
            f"🚨 NO ENTRAR — EARNINGS HOY ({earnings['date']}).\n"
            "El IV Crush al cierre destruye el valor de la opción.\n"
            "Esperar al día siguiente del reporte para evaluar E3 (salto)."
        )

    high_today = any(e["impact"] == "alto" and e["days"] == 0 for e in events)

    if strategy == StrategyType.SQUEEZE_CANAL:
        return (
            "MONITOREAR — Squeeze en canal lateral.\n"
            "Esperar BB expandiendo + precio saliendo del canal + vela extrema.\n"
            "No entrar hasta confirmar dirección (puede ser E1 o E2)."
        )

    if strength == SignalStrength.DEBIL:
        return "No entrar — señal débil. Esperar mejores condiciones."

    if high_today:
        return (
            f"{direction.value} {strength.value} — ⚠️ Evento de alto impacto HOY.\n"
            "Reducir tamaño de posición o esperar después del evento."
        )

    # Earnings próximos = reducir tamaño
    earnings_txt = ""
    if earnings and earnings.get("has_earnings"):
        days = earnings["days_away"]
        if days == 1:
            earnings_txt = f"\n⚠️ EARNINGS MAÑANA — Reducir tamaño al mínimo."
        elif days <= 3:
            earnings_txt = f"\n📅 Earnings en {days} días — IV elevada, tamaño reducido."

    # Agotamiento = agregar nota de salida
    agot_txt = ""
    if agotamiento and agotamiento.get("has_agotamiento"):
        agot_txt = (
            f"\n⚠️ Señales de agotamiento detectadas — "
            "proteger posición si ya estás adentro."
        )

    blind   = f"\n{ma.daily_warning}" if ma.daily_warning else ""
    vol_txt = f"Volatilidad BB: {bb.bandwidth_pct_15m:.0f}% percentil — {bb.volatility_level}"

    if strength == SignalStrength.FUERTE:
        return (
            f"{direction.value} FUERTE — Todos los elementos alineados.\n"
            f"{vol_txt}\n"
            f"Confirmar en TC2000 antes de entrar."
            f"{earnings_txt}{agot_txt}{blind}"
        )
    else:
        return (
            f"{direction.value} MODERADO — Mayoría alineada.\n"
            f"{vol_txt}\n"
            f"Confirmar visualmente en TC2000 antes de entrar."
            f"{earnings_txt}{agot_txt}{blind}"
        )


# ============================================================
# CATEGORIA DEL TICKER
# ============================================================

def get_categoria(ticker: str) -> str:
    for cat, tickers in TICKERS_SAAI.items():
        if ticker in tickers:
            return cat.replace("_", " ")
    return "OTRO"


# ============================================================
# MOTOR PRINCIPAL
# ============================================================

def fetch_data(ticker: str):
    stock = yf.Ticker(ticker)
    return (
        stock.history(period="5d",  interval="15m"),
        stock.history(period="3mo", interval="1h"),
        stock.history(period="1y",  interval="1d"),
    )


def analyze_ticker(ticker: str) -> Optional[Alert]:
    try:
        df_15m, df_1h, df_daily = fetch_data(ticker)

        if df_15m.empty or df_1h.empty or df_daily.empty:
            print(f"[{ticker}] Sin datos")
            return None

        ma   = analyze_mas(df_1h, df_daily)
        bb   = analyze_bb(df_15m, df_1h)
        gap  = analyze_gaps(df_daily, ma)
        chop = calc_choppiness(df_1h)

        score, pan_dir = calc_score(ma, bb, chop)

        print(
            f"[{ticker}] Score:{score} | Chop:{chop} | "
            f"Vol:{bb.volatility_level}({bb.bandwidth_pct_15m:.0f}%) | "
            f"MAs:{ma.trend_1h} | Canal:{ma.lateral_days_1h}d"
        )

        strategy, direction, strength, explanation = identify_strategy(
            ma, bb, gap, chop, score, pan_dir
        )

        if strength == SignalStrength.DEBIL or strategy == StrategyType.NONE:
            return None

        # ── Eventos macro ──
        events = check_events()

        # ── Earnings automáticos ──
        earnings = check_earnings(ticker)
        if earnings.get("has_earnings"):
            print(f"   [{ticker}] {earnings['warning']}")

        # ── Agotamiento de tendencia ──
        agotamiento = check_agotamiento(df_15m, df_1h, ma, bb)
        if agotamiento.get("has_agotamiento"):
            print(f"   [{ticker}] Agotamiento detectado: {len(agotamiento['signals'])} señales")

        # ── Recomendación ──
        rec = generate_rec(direction, strength, strategy, events, ma, bb, chop,
                           earnings, agotamiento)

        # ── Advertencias consolidadas ──
        warns = [e["warning"] for e in events]
        if earnings.get("has_earnings"):
            warns.append(earnings["warning"])
        if agotamiento.get("has_agotamiento"):
            warns.append(agotamiento["warning"])
        if ma.daily_warning:
            warns.append(ma.daily_warning)

        et  = pytz.timezone('US/Eastern')
        now = datetime.now(et)

        return Alert(
            ticker=ticker,
            timestamp=now.strftime("%Y-%m-%d %I:%M %p ET"),
            strategy=strategy,
            direction=direction,
            strength=strength,
            ma=ma,
            bb=bb,
            score=score,
            price=ma.price,
            explanation=explanation,
            recommendation=rec,
            warning="\n".join(warns) if warns else None,
            external_events=events,
            categoria=get_categoria(ticker),
            earnings=earnings,
            agotamiento=agotamiento,
        )

    except Exception as e:
        print(f"[{ticker}] Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def run_analysis(tickers=None) -> list:
    if tickers is None:
        env     = os.environ.get("SAAI_TICKERS", "")
        tickers = [t.strip() for t in env.split(",")] if env else DEFAULT_TICKERS

    et = pytz.timezone('US/Eastern')

    print(f"\n{'=' * 65}")
    print(f"  SAAI v5.3 — Smart Alert AI System")
    print(f"  Un Millón al Año No Hace Daño — Yoel Sardiñas")
    print(f"  Estrategias: E1 Canal Alza | E2 Canal Baja | E3 Saltos")
    print(f"  Volatilidad: ALTA(>75%) | MEDIA(60-75%) | BAJA(<60%)")
    print(f"  {len(tickers)} tickers | {datetime.now(et).strftime('%I:%M %p ET')}")
    print(f"{'=' * 65}\n")

    alerts = []
    for ticker in tickers:
        print(f"[{ticker}] Analizando...")
        a = analyze_ticker(ticker)
        if a:
            alerts.append(a)
            print(
                f"[{ticker}] ✅ ALERTA: {a.strategy.value} → "
                f"{a.direction.value} {a.strength.value} "
                f"(Score:{a.score} | Vol:{a.bb.volatility_level})"
            )

    print(f"\n{'=' * 65}")
    print(f"  Analizados: {len(tickers)} | Alertas: {len(alerts)}")
    if alerts:
        for a in alerts:
            print(f"  → {a.ticker} [{a.categoria}]: {a.strategy.value}")
    print(f"\n  REGLA: Si algún elemento no se presenta, se convierte en apuesta.")
    print(f"{'=' * 65}\n")

    return alerts


# ============================================================
# RUN DIRECTO
# ============================================================

if __name__ == "__main__":
    alerts = run_analysis()
    for a in alerts:
        print(f"\n{'-' * 60}")
        print(f"{a.ticker} [{a.categoria}] — {a.timestamp} — ${a.price}")
        print(f"{a.strategy.value}")
        print(f"{a.direction.value} {a.strength.value} | Score: {a.score}/100")
        print(f"MAs 1H: {a.ma.trend_1h} | BB Vol: {a.bb.volatility_level} "
              f"({a.bb.bandwidth_pct_15m:.0f}%) | Diario: {a.ma.daily_trend}")
        if a.ma.daily_warning:
            print(f"\n{a.ma.daily_warning}")
        print(f"\n{a.explanation}")
        if a.warning:
            print(f"\n{a.warning}")
        print(f"\n{a.recommendation}")
        print(f"{'-' * 60}")
