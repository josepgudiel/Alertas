# SAAI v4 - Smart Alert AI System
# Motor de Analisis - LOGICA CORRECTA
# Basado en Un Millon al Anno No Hace Danno - Yoel Sardinas
# UMBRALES: score < 50 = no alerta | 50-60 = MODERADO | > 60 = FUERTE
# MAs decision en 1H | BB decision en 15min | Diario = puntos ciegos

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import pytz


# ============================================================
# ENUMS & DATA CLASSES
# ============================================================

class SignalDirection(Enum):
    CALL = "CALL"
    PUT = "PUT"
    NEUTRAL = "NEUTRAL"

class SignalStrength(Enum):
    FUERTE = "FUERTE"
    MODERADO = "MODERADO"
    DEBIL = "DEBIL"

class StrategyType(Enum):
    CANAL_LATERAL_ALZA     = "Estrategia 1 -- Canal Lateral al Alza"
    CANAL_LATERAL_BAJA     = "Estrategia 2 -- Canal Lateral a la Baja"
    SALTO_ALCISTA          = "Estrategia 3 -- Salto Alcista"
    SALTO_BAJISTA          = "Estrategia 3 -- Salto Bajista"
    SALTO_CAMBIO_TENDENCIA = "Estrategia 3 -- Salto Cambio de Tendencia"
    BB_SALIDA_CALL         = "BB Salida de Banda -- CALL"
    BB_SALIDA_PUT          = "BB Salida de Banda -- PUT"
    BB_ACERCAMIENTO_CALL   = "BB Acercamiento con Volatilidad -- CALL"
    BB_ACERCAMIENTO_PUT    = "BB Acercamiento con Volatilidad -- PUT"
    REBOTE_MA_CALL         = "Rebote en MA como Piso -- CALL"
    REBOTE_MA_PUT          = "Rebote en MA como Techo -- PUT"
    SQUEEZE                = "Squeeze -- Explosion Inminente"
    AGOTAMIENTO            = "! Agotamiento de Estrategia"
    NONE                   = "Sin estrategia"


@dataclass
class MADecision:
    ma20_1h: float
    ma40_1h: float
    ma100_1h: float
    ma200_1h: float
    price: float
    trend_1h: str
    bullish_pts_1h: int
    is_lateral_1h: bool
    lateral_days_1h: int
    price_above_all_1h: bool
    price_below_all_1h: bool
    bouncing_on: Optional[str]
    bounce_dir: str
    nearest_support: Optional[str]
    nearest_resistance: Optional[str]
    daily_blind_spots: list
    daily_trend: str
    daily_ma200: float
    daily_warning: Optional[str]


@dataclass
class BBDecision:
    upper_15m: float
    lower_15m: float
    mid_15m: float
    bandwidth_15m: float
    prev_bandwidth_15m: float
    is_expanding_15m: bool
    is_squeeze_15m: bool
    is_high_volatility_15m: bool
    bandwidth_pct_15m: float
    price_above_upper_15m: bool
    price_below_lower_15m: bool
    price_near_upper_15m: bool
    price_near_lower_15m: bool
    expansion_pct_15m: float
    bb_contracting_15m: bool
    bb_expanding_1h: bool
    bb_squeeze_1h: bool
    bb_pct_1h: float
    candle_type: str


@dataclass
class Alert:
    ticker: str
    timestamp: str
    strategy: StrategyType
    direction: SignalDirection
    strength: SignalStrength
    ma: MADecision
    bb: BBDecision
    score: float
    price: float
    explanation: str
    recommendation: str
    warning: Optional[str]
    external_events: list


# ============================================================
# MEDIAS MOVILES -- DECISION EN 1H / DIARIO -- PUNTOS CIEGOS
# ============================================================

def analyze_mas(df_1h: pd.DataFrame, df_daily: pd.DataFrame) -> MADecision:
    if len(df_1h) < 200:
        price = df_1h['Close'].iloc[-1] if len(df_1h) > 0 else 0
        return _empty_ma(price)

    close_1h = df_1h['Close']
    price = close_1h.iloc[-1]

    ma20  = close_1h.rolling(20).mean().iloc[-1]
    ma40  = close_1h.rolling(40).mean().iloc[-1]
    ma100 = close_1h.rolling(100).mean().iloc[-1]
    ma200 = close_1h.rolling(200).mean().iloc[-1]

    bp = sum([ma20>ma40, ma40>ma100, ma100>ma200])
    trend = {3:"alcista_fuerte", 2:"alcista_parcial",
             1:"bajista_parcial", 0:"bajista_fuerte"}.get(bp, "lateral")

    is_lat, lat_days = _detect_lateral(df_1h)
    bouncing, bounce_dir = _detect_bounce(df_1h, ma20, ma40, ma100, ma200, price)
    support, resistance = _nearest_levels(price, ma20, ma40, ma100, ma200)

    blind_spots = []
    daily_warning = None
    d_ma200 = price
    d_trend = "desconocido"

    if len(df_daily) >= 200:
        d_close = df_daily['Close']
        d_ma20  = d_close.rolling(20).mean().iloc[-1]
        d_ma40  = d_close.rolling(40).mean().iloc[-1]
        d_ma100 = d_close.rolling(100).mean().iloc[-1]
        d_ma200 = d_close.rolling(200).mean().iloc[-1]

        d_bp = sum([d_ma20>d_ma40, d_ma40>d_ma100, d_ma100>d_ma200])
        d_trend = {3:"alcista_fuerte", 2:"alcista_parcial",
                   1:"bajista_parcial", 0:"bajista_fuerte"}.get(d_bp, "lateral")

        daily_levels = {
            "MA20 Diario": d_ma20,
            "MA40 Diario": d_ma40,
            "MA100 Diario": d_ma100,
            "MA200 Diario (Institucional)": d_ma200
        }

        warnings = []
        for name, val in daily_levels.items():
            dist_pct = abs(price - val) / price * 100
            if dist_pct < 1.5:
                direction_txt = "RESISTENCIA" if val > price else "SOPORTE"
                blind_spots.append(f"{name}: ${val:.2f} ({direction_txt})")
                warnings.append(
                    f"! PUNTO CIEGO: {name} en ${val:.2f} actuando como "
                    f"{direction_txt} -- nivel que no se ve claramente en 1H"
                )

        if warnings:
            daily_warning = "\n".join(warnings)

    return MADecision(
        ma20_1h=round(ma20,2), ma40_1h=round(ma40,2),
        ma100_1h=round(ma100,2), ma200_1h=round(ma200,2),
        price=round(price,2), trend_1h=trend, bullish_pts_1h=bp,
        is_lateral_1h=is_lat, lateral_days_1h=lat_days,
        price_above_all_1h=price > max(ma20,ma40,ma100,ma200),
        price_below_all_1h=price < min(ma20,ma40,ma100,ma200),
        bouncing_on=bouncing, bounce_dir=bounce_dir,
        nearest_support=support, nearest_resistance=resistance,
        daily_blind_spots=blind_spots, daily_trend=d_trend,
        daily_ma200=round(d_ma200,2), daily_warning=daily_warning
    )


def _detect_lateral(df: pd.DataFrame, min_days: int = 10) -> tuple:
    ma20  = df['Close'].rolling(20).mean()
    ma40  = df['Close'].rolling(40).mean()
    ma100 = df['Close'].rolling(100).mean()
    ma200 = df['Close'].rolling(200).mean()
    bars_per_day = 7
    count = 0
    for i in range(-1, -len(df), -1):
        try:
            mas = [ma20.iloc[i], ma40.iloc[i], ma100.iloc[i], ma200.iloc[i]]
            if any(pd.isna(m) for m in mas): break
            spread = (max(mas) - min(mas)) / df['Close'].iloc[i] * 100
            if spread < 3.0: count += 1
            else: break
        except: break
    days = count // max(bars_per_day, 1)
    return days >= min_days, days


def _detect_bounce(df, ma20, ma40, ma100, ma200, price) -> tuple:
    lookback = min(5, len(df))
    if lookback < 2: return None, "none"
    lows  = df['Low'].iloc[-lookback:].values
    highs = df['High'].iloc[-lookback:].values
    levels = {"MA20":ma20, "MA40":ma40, "MA100":ma100, "MA200":ma200}
    for name, val in levels.items():
        if any(abs(l - val)/val < 0.005 for l in lows) and price > val:
            return name, "up"
        if any(abs(h - val)/val < 0.005 for h in highs) and price < val:
            return name, "down"
    return None, "none"


def _nearest_levels(price, ma20, ma40, ma100, ma200) -> tuple:
    levels = {"MA20":ma20, "MA40":ma40, "MA100":ma100, "MA200":ma200}
    supports    = {k:v for k,v in levels.items() if v < price}
    resistances = {k:v for k,v in levels.items() if v > price}
    return (max(supports, key=supports.get) if supports else None,
            min(resistances, key=resistances.get) if resistances else None)


def _empty_ma(price: float) -> MADecision:
    return MADecision(
        ma20_1h=price, ma40_1h=price, ma100_1h=price, ma200_1h=price,
        price=price, trend_1h="lateral", bullish_pts_1h=0,
        is_lateral_1h=False, lateral_days_1h=0,
        price_above_all_1h=False, price_below_all_1h=False,
        bouncing_on=None, bounce_dir="none",
        nearest_support=None, nearest_resistance=None,
        daily_blind_spots=[], daily_trend="desconocido",
        daily_ma200=price, daily_warning=None
    )


# ============================================================
# BOLLINGER BANDS -- DECISION EN 15MIN
# ============================================================

def analyze_bb(df_15m: pd.DataFrame, df_1h: pd.DataFrame) -> BBDecision:
    def _calc_bb(df, length=20, num_std=2.0):
        if len(df) < length + 5:
            c = df['Close'].iloc[-1] if len(df) > 0 else 0
            return c, c, c, 0, 0, False, False, False, 50.0, False, False, False, False, 0, False
        close = df['Close']
        c = close.iloc[-1]
        sma = close.rolling(length).mean()
        std = close.rolling(length).std()
        upper = sma + num_std * std
        lower = sma - num_std * std
        cu = upper.iloc[-1]; cl = lower.iloc[-1]; cm = sma.iloc[-1]
        bw = (cu - cl) / cm if cm > 0 else 0
        prev_bw = ((upper.iloc[-2] - lower.iloc[-2]) / sma.iloc[-2]) if len(sma) > 1 and sma.iloc[-2] > 0 else bw
        expanding = bw > prev_bw * 1.05
        exp_pct = ((bw - prev_bw) / prev_bw * 100) if prev_bw > 0 else 0
        bw_series = ((upper - lower) / sma).dropna()
        avg_bw = bw_series.rolling(20).mean().iloc[-1] if len(bw_series) >= 20 else bw
        squeeze = bw < avg_bw * 0.75
        recent = bw_series.tail(50)
        pct = float((recent < bw).mean() * 100) if len(recent) > 0 else 50.0
        high_vol = pct > 60 and expanding
        above = c > cu; below = c < cl
        band_range = cu - cl
        near_upper = (not above) and band_range > 0 and (cu - c) < band_range * 0.08 and expanding
        near_lower = (not below) and band_range > 0 and (c - cl) < band_range * 0.08 and expanding
        contracting = False
        if len(bw_series) >= 4:
            last = bw_series.tail(4).values
            if all(last[i] > last[i+1] for i in range(len(last)-1)):
                contracting = True
        return cu, cl, cm, bw, prev_bw, expanding, squeeze, high_vol, pct, above, below, near_upper, near_lower, exp_pct, contracting

    (u15, l15, m15, bw15, pbw15, exp15, sq15, hv15, pct15,
     ab15, bl15, nu15, nl15, epct15, con15) = _calc_bb(df_15m)
    (u1h, l1h, m1h, bw1h, pbw1h, exp1h, sq1h, hv1h, pct1h,
     ab1h, bl1h, nu1h, nl1h, epct1h, con1h) = _calc_bb(df_1h)
    candle = _candle_type(df_15m)

    return BBDecision(
        upper_15m=round(u15,2), lower_15m=round(l15,2), mid_15m=round(m15,2),
        bandwidth_15m=round(bw15,6), prev_bandwidth_15m=round(pbw15,6),
        is_expanding_15m=exp15, is_squeeze_15m=sq15,
        is_high_volatility_15m=hv15, bandwidth_pct_15m=round(pct15,1),
        price_above_upper_15m=ab15, price_below_lower_15m=bl15,
        price_near_upper_15m=nu15, price_near_lower_15m=nl15,
        expansion_pct_15m=round(epct15,2), bb_contracting_15m=con15,
        bb_expanding_1h=exp1h, bb_squeeze_1h=sq1h, bb_pct_1h=round(pct1h,1),
        candle_type=candle
    )


def _candle_type(df: pd.DataFrame) -> str:
    if len(df) == 0: return "normal"
    last = df.iloc[-1]
    op, hi, lo, cl = last['Open'], last['High'], last['Low'], last['Close']
    rng = hi - lo
    if rng == 0: return "doji"
    body = abs(cl - op) / rng * 100
    if body > 70:
        return "extreme_bullish" if cl > op else "extreme_bearish"
    return "doji" if body < 15 else "normal"


# ============================================================
# CHOPPINESS
# ============================================================

def calc_choppiness(df_1h: pd.DataFrame, n: int = 14) -> float:
    if len(df_1h) < n + 2: return 50.0
    try:
        hi = df_1h['High'].tail(n+1)
        lo = df_1h['Low'].tail(n+1)
        cl = df_1h['Close'].tail(n+1)
        tr = pd.concat([hi-lo, (hi-cl.shift(1)).abs(), (lo-cl.shift(1)).abs()], axis=1).max(axis=1)
        atr_sum = tr.tail(n).sum()
        hl = hi.tail(n).max() - lo.tail(n).min()
        if hl == 0: return 50.0
        return round(float(100 * np.log10(atr_sum / hl) / np.log10(n)), 1)
    except: return 50.0


# ============================================================
# EVENTOS EXTERNOS
# ============================================================

ECONOMIC_CALENDAR = {
    "2026-04-30": {"name": "FOMC Decision", "impact": "alto"},
    "2026-05-01": {"name": "Jobs Report (NFP)", "impact": "alto"},
    "2026-05-06": {"name": "FOMC Decision", "impact": "alto"},
    "2026-05-13": {"name": "CPI Report", "impact": "alto"},
    "2026-05-15": {"name": "OpEx Mensual", "impact": "medio"},
    "2026-06-10": {"name": "CPI Report", "impact": "alto"},
    "2026-06-17": {"name": "FOMC Decision", "impact": "alto"},
    "2026-06-19": {"name": "OpEx Mensual", "impact": "medio"},
    "2026-07-02": {"name": "Jobs Report (NFP)", "impact": "alto"},
    "2026-07-15": {"name": "CPI Report", "impact": "alto"},
    "2026-07-17": {"name": "OpEx Mensual", "impact": "medio"},
    "2026-07-29": {"name": "FOMC Decision", "impact": "alto"},
}


def check_events() -> list:
    et = pytz.timezone('US/Eastern')
    now = datetime.now(et)
    events = []
    for i, label in {0:"HOY", 1:"MANANA", 2:"En 2 dias"}.items():
        d = (now + timedelta(days=i)).strftime("%Y-%m-%d")
        if d in ECONOMIC_CALENDAR:
            ev = ECONOMIC_CALENDAR[d]
            if i == 0:   warn = f"! HOY: {ev['name']} -- Maxima cautela"
            elif i == 1: warn = f" MANANA: {ev['name']} -- Reducir tamano"
            else:        warn = f" En 2 dias: {ev['name']} -- Tener en cuenta"
            events.append({"name": ev['name'], "impact": ev['impact'], "warning": warn, "days": i})
    return events


# ============================================================
# GAPS -- ESTRATEGIA 3
# ============================================================

def analyze_gaps(df_daily: pd.DataFrame, ma: MADecision) -> dict:
    if len(df_daily) < 2: return {"has_gap": False}
    today_open  = df_daily['Open'].iloc[-1]
    today_close = df_daily['Close'].iloc[-1]
    yest_close  = df_daily['Close'].iloc[-2]
    size = today_open - yest_close
    pct  = (size / yest_close * 100) if yest_close > 0 else 0
    if abs(pct) <= 0.3: return {"has_gap": False}
    direction = "up" if size > 0 else "down"
    is_reversal = (
        (direction == "up"   and ma.trend_1h in ["bajista_fuerte","bajista_parcial"]) or
        (direction == "down" and ma.trend_1h in ["alcista_fuerte","alcista_parcial"])
    )
    gap_filled = (
        (direction == "up"   and today_close < yest_close) or
        (direction == "down" and today_close > yest_close)
    )
    if direction == "up" and today_close > today_open:     second_prob = 0.90
    elif direction == "down" and today_close < today_open: second_prob = 0.90
    elif gap_filled:                                       second_prob = 0.10
    else:                                                  second_prob = 0.50
    return {
        "has_gap": True, "direction": direction,
        "size": round(abs(size),2), "pct": round(abs(pct),3),
        "is_reversal": is_reversal, "gap_filled": gap_filled,
        "second_prob": second_prob
    }


# ============================================================
# SCORING
# ============================================================

def calc_score(ma: MADecision, bb: BBDecision, gap: dict, chop: float) -> tuple:
    # BB 15min = hasta 50 pts | MAs 1H = hasta 40 pts | Diario = hasta 10 pts
    # UMBRALES: < 50 = DEBIL | 50-60 = MODERADO | > 60 = FUERTE
    score = 0.0
    bullish = 0
    bearish = 0

    # BB 15min -- hasta 50 pts
    if bb.is_high_volatility_15m:
        score += 20
        if bb.price_above_upper_15m:
            score += 25; bearish += 2
        elif bb.price_below_lower_15m:
            score += 25; bullish += 2
        elif bb.price_near_upper_15m:
            score += 12; bearish += 1
        elif bb.price_near_lower_15m:
            score += 12; bullish += 1
    elif bb.is_expanding_15m:
        score += 12
    elif bb.is_squeeze_15m:
        score += 8

    # MAs 1H -- hasta 40 pts
    if ma.trend_1h == "alcista_fuerte":
        score += 40; bullish += 3
    elif ma.trend_1h == "alcista_parcial":
        score += 28; bullish += 2
    elif ma.trend_1h == "bajista_fuerte":
        score += 40; bearish += 3
    elif ma.trend_1h == "bajista_parcial":
        score += 28; bearish += 2
    elif ma.is_lateral_1h:
        score += 15

    if ma.price_above_all_1h:
        score = min(score + 5, 90); bullish += 1
    elif ma.price_below_all_1h:
        score = min(score + 5, 90); bearish += 1

    # Diario -- hasta 10 pts
    if ma.daily_trend == "alcista_fuerte":
        score += 10; bullish += 1
    elif ma.daily_trend == "alcista_parcial":
        score += 6; bullish += 1
    elif ma.daily_trend == "bajista_fuerte":
        score += 10; bearish += 1
    elif ma.daily_trend == "bajista_parcial":
        score += 6; bearish += 1

    # Penalizacion choppy
    if chop > 61.8:
        score *= 0.5

    direction = "alcista" if bullish > bearish else "bajista" if bearish > bullish else "mixto"
    return round(score, 1), direction


def score_to_strength(score: float) -> SignalStrength:
    # Convierte score: < 50 = DEBIL | 50-60 = MODERADO | > 60 = FUERTE
    if score > 60:
        return SignalStrength.FUERTE
    elif score >= 50:
        return SignalStrength.MODERADO
    else:
        return SignalStrength.DEBIL


# ============================================================
# IDENTIFICADOR DE ESTRATEGIAS
# ============================================================

def identify_strategy(ma, bb, gap, chop, score, pan_direction) -> tuple:

    # Filtro mercado choppy
    if chop > 61.8 and not gap.get("has_gap"):
        return StrategyType.NONE, SignalDirection.NEUTRAL, SignalStrength.DEBIL, ""

    # Filtro score minimo 50
    if score < 50 and not gap.get("has_gap"):
        return StrategyType.NONE, SignalDirection.NEUTRAL, SignalStrength.DEBIL, ""

    strength = score_to_strength(score)

    # Agotamiento
    if bb.bb_contracting_15m and bb.bandwidth_pct_15m < 35:
        exp = (
            f"! AGOTAMIENTO DETECTADO.\n"
            f"BB 15min contrayendose -- volatilidad cediendo.\n"
            f"MAs 1H: {ma.trend_1h}\n"
            f"Del libro: 'Nada sube para siempre y nada baja para siempre.'\n"
            f"Si tienes posicion abierta, considera salir."
        )
        d = SignalDirection.PUT if pan_direction == "alcista" else SignalDirection.CALL
        return StrategyType.AGOTAMIENTO, d, SignalStrength.MODERADO, exp

    # Estrategia 3: Saltos
    if gap.get("has_gap"):
        return _strategy_saltos(gap, ma, bb, score)

    # Estrategia 1 y 2: Canal Lateral
    if ma.is_lateral_1h and ma.lateral_days_1h >= 10:
        result = _strategy_canal(ma, bb, score)
        if result[0] != StrategyType.NONE:
            return result

    # BB Salida de Banda
    if bb.price_above_upper_15m or bb.price_below_lower_15m:
        result = _strategy_bb_salida(ma, bb, score, pan_direction)
        if result[0] != StrategyType.NONE:
            return result

    # BB Acercamiento
    if bb.price_near_upper_15m or bb.price_near_lower_15m:
        result = _strategy_bb_acercamiento(ma, bb, score, pan_direction)
        if result[0] != StrategyType.NONE:
            return result

    # Rebote en MA
    if ma.bouncing_on and bb.is_expanding_15m:
        result = _strategy_rebote(ma, bb, score)
        if result[0] != StrategyType.NONE:
            return result

    # Squeeze
    if bb.is_squeeze_15m:
        days_txt = f" -- canal lateral {ma.lateral_days_1h} dias" if ma.is_lateral_1h else ""
        exp = (
            f"SQUEEZE en BB 15min -- explosion inminente{days_txt}.\n"
            f"MAs 1H: {ma.trend_1h}\n"
            f"Diario: {ma.daily_trend}\n"
            f"! Esperar BB expandiendo con alta volatilidad antes de entrar."
        )
        return StrategyType.SQUEEZE, SignalDirection.NEUTRAL, SignalStrength.MODERADO, exp

    return StrategyType.NONE, SignalDirection.NEUTRAL, SignalStrength.DEBIL, ""


def _strategy_saltos(gap, ma, bb, score) -> tuple:
    if gap["gap_filled"]:
        d = SignalDirection.CALL if gap["direction"] == "down" else SignalDirection.PUT
        exp = (
            f"! CAMBIO DE TENDENCIA INMINENTE -- Regla 4 del libro.\n"
            f"Gap {gap['direction'].upper()} de ${gap['size']} que se revirtio al cierre.\n"
            f"MAs 1H: {ma.trend_1h} | Diario: {ma.daily_trend}\n"
            f"Del libro: 'Si el precio abre hacia una direccion y al cierre va en direccion\n"
            f"contraria, borrando la historia del precio del dia, indica cambio de tendencia.'\n"
            f"! NO continuar en la direccion original del gap."
        )
        return StrategyType.SALTO_CAMBIO_TENDENCIA, d, SignalStrength.MODERADO, exp

    second = f"\n Prob. segundo salto manana: {int(gap['second_prob']*100)}%" if gap["second_prob"] >= 0.5 else ""
    strength = score_to_strength(score)

    if gap["direction"] == "up":
        if ma.trend_1h in ["alcista_fuerte","alcista_parcial"]:
            exp = (
                f"ESTRATEGIA 3 -- SALTO ALCISTA en apertura.\n"
                f"Gap alcista: +${gap['size']} (+{gap['pct']}%) vs cierre anterior.\n\n"
                f"MAs 1H: {ma.trend_1h} (DECISION)\n"
                f"BB 15min: percentil {bb.bandwidth_pct_15m:.0f}% (ENTRADA){second}\n"
                f"Diario: {ma.daily_trend} (contexto)\n"
                f"Score: {score}/100\n\n"
                f"Del libro: 'Cuando ocurre un primer salto, el precio continuara\n"
                f"en la direccion del salto en un alto porcentaje de las veces.' -- 90%."
            )
            return StrategyType.SALTO_ALCISTA, SignalDirection.CALL, strength, exp
        elif gap["is_reversal"]:
            exp = (
                f"ESTRATEGIA 3 -- SALTO ALCISTA CONTRA TENDENCIA (Regla 3).\n"
                f"Gap alcista de ${gap['size']} en tendencia bajista.\n"
                f"MAs 1H: {ma.trend_1h} | Diario: {ma.daily_trend}\n"
                f"Del libro: Posible cambio de tendencia inminente.\n"
                f"! Monitorear el dia -- si cierra alcista: 90% segundo salto manana."
            )
            return StrategyType.SALTO_ALCISTA, SignalDirection.CALL, SignalStrength.MODERADO, exp

    elif gap["direction"] == "down":
        if ma.trend_1h in ["bajista_fuerte","bajista_parcial"]:
            exp = (
                f"ESTRATEGIA 3 -- SALTO BAJISTA en apertura.\n"
                f"Gap bajista: -${gap['size']} (-{gap['pct']}%) vs cierre anterior.\n\n"
                f"MAs 1H: {ma.trend_1h} (DECISION)\n"
                f"BB 15min: percentil {bb.bandwidth_pct_15m:.0f}% (ENTRADA){second}\n"
                f"Diario: {ma.daily_trend} (contexto)\n"
                f"Score: {score}/100\n\n"
                f"Del libro: 90% de probabilidad de continuacion bajista."
            )
            return StrategyType.SALTO_BAJISTA, SignalDirection.PUT, strength, exp
        elif gap["is_reversal"]:
            exp = (
                f"ESTRATEGIA 3 -- SALTO BAJISTA CONTRA TENDENCIA (Regla 3).\n"
                f"Gap bajista de ${gap['size']} en tendencia alcista.\n"
                f"MAs 1H: {ma.trend_1h} | Diario: {ma.daily_trend}\n"
                f"Posible cambio de tendencia segun el libro."
            )
            return StrategyType.SALTO_BAJISTA, SignalDirection.PUT, SignalStrength.MODERADO, exp

    return StrategyType.NONE, SignalDirection.NEUTRAL, SignalStrength.DEBIL, ""


def _strategy_canal(ma, bb, score) -> tuple:
    days = ma.lateral_days_1h
    strength = score_to_strength(score)

    if bb.is_high_volatility_15m and bb.price_above_upper_15m:
        candle_txt = "Vela extremadamente alcista en 15min -- confirmacion del libro.\n" if bb.candle_type == "extreme_bullish" else ""
        exp = (
            f"ESTRATEGIA 1 -- CANAL LATERAL AL ALZA.\n\n"
            f"MAs 1H: canal lateral {days} dias -- MAs entrelazadas (DECISION)\n"
            f"Precio rompio el canal al ALZA.\n"
            f"{candle_txt}"
            f"BB 15min: alta volatilidad {bb.bandwidth_pct_15m:.0f}% percentil -- CONFIRMADA (ENTRADA)\n"
            f"Diario: {ma.daily_trend} (contexto)\n"
            f"Score: {score}/100\n\n"
            f"Del libro: 'Las cuatro MAs deben mostrarse laterales 10+ dias.\n"
            f"Esperar confirmacion con vela final alcista en BB 15min con alta volatilidad.'\n"
            f"Rentabilidades historicas: 100% a 3000% en 2-5 dias."
        )
        return StrategyType.CANAL_LATERAL_ALZA, SignalDirection.CALL, strength, exp

    elif bb.is_high_volatility_15m and bb.price_below_lower_15m:
        candle_txt = "Vela extremadamente bajista en 15min -- confirmacion del libro.\n" if bb.candle_type == "extreme_bearish" else ""
        exp = (
            f"ESTRATEGIA 2 -- CANAL LATERAL A LA BAJA.\n\n"
            f"MAs 1H: canal lateral {days} dias -- MAs entrelazadas (DECISION)\n"
            f"Precio rompio el canal a la BAJA.\n"
            f"{candle_txt}"
            f"BB 15min: alta volatilidad {bb.bandwidth_pct_15m:.0f}% percentil -- CONFIRMADA (ENTRADA)\n"
            f"Diario: {ma.daily_trend} (contexto)\n"
            f"Score: {score}/100\n\n"
            f"Del libro: Rentabilidades historicas: 100% a 3000% en 2-5 dias."
        )
        return StrategyType.CANAL_LATERAL_BAJA, SignalDirection.PUT, strength, exp

    elif bb.is_squeeze_15m:
        exp = (
            f"SQUEEZE en canal lateral de {days} dias.\n"
            f"MAs 1H: {days} dias entrelazadas (DECISION)\n"
            f"BB 15min: squeeze -- explosion inminente (ENTRADA proxima)\n"
            f"Score: {score}/100\n"
            f"! Esperar BB expandiendo con alta volatilidad -- puede ser E1 o E2."
        )
        return StrategyType.SQUEEZE, SignalDirection.NEUTRAL, SignalStrength.MODERADO, exp

    return StrategyType.NONE, SignalDirection.NEUTRAL, SignalStrength.DEBIL, ""


def _strategy_bb_salida(ma, bb, score, pan_dir) -> tuple:
    if not bb.is_high_volatility_15m:
        return StrategyType.NONE, SignalDirection.NEUTRAL, SignalStrength.DEBIL, ""

    strength = score_to_strength(score)
    sr_txt = f"Rebotando en {ma.bouncing_on} como {'PISO' if ma.bounce_dir=='up' else 'TECHO'}.\n" if ma.bouncing_on else ""
    support_txt = f"Soporte proximo: {ma.nearest_support} | Resistencia: {ma.nearest_resistance}\n" if ma.nearest_support or ma.nearest_resistance else ""

    if bb.price_above_upper_15m:
        if ma.trend_1h in ["bajista_fuerte","bajista_parcial"]:
            exp = (
                f"BB SALIDA BANDA SUPERIOR -- Panorama bajista -> PUT.\n\n"
                f"BB 15min: precio SALIO de banda superior -- percentil {bb.bandwidth_pct_15m:.0f}% (ENTRADA)\n"
                f"MAs 1H: {ma.trend_1h} -- tendencia bajista (DECISION)\n"
                f"{sr_txt}{support_txt}"
                f"Diario: {ma.daily_trend} (contexto)\n"
                f"Score: {score}/100\n\n"
                f"Sobreextension alcista con MAs bajistas en 1H -- posible reversion."
            )
            return StrategyType.BB_SALIDA_PUT, SignalDirection.PUT, strength, exp
        elif ma.trend_1h in ["alcista_fuerte","alcista_parcial"]:
            exp = (
                f"BB SALIDA BANDA SUPERIOR -- Ruptura alcista fuerte -> CALL.\n\n"
                f"BB 15min: precio SALIO de banda superior -- percentil {bb.bandwidth_pct_15m:.0f}% (ENTRADA)\n"
                f"MAs 1H: {ma.trend_1h} -- tendencia alcista (DECISION)\n"
                f"{sr_txt}{support_txt}"
                f"Diario: {ma.daily_trend} (contexto)\n"
                f"Score: {score}/100\n\n"
                f"Ruptura con MAs alcistas en 1H -- continuacion del movimiento."
            )
            return StrategyType.BB_SALIDA_CALL, SignalDirection.CALL, strength, exp

    elif bb.price_below_lower_15m:
        if ma.trend_1h in ["alcista_fuerte","alcista_parcial"]:
            exp = (
                f"BB SALIDA BANDA INFERIOR -- Panorama alcista -> CALL.\n\n"
                f"BB 15min: precio SALIO de banda inferior -- percentil {bb.bandwidth_pct_15m:.0f}% (ENTRADA)\n"
                f"MAs 1H: {ma.trend_1h} -- tendencia alcista (DECISION)\n"
                f"{sr_txt}{support_txt}"
                f"Diario: {ma.daily_trend} (contexto)\n"
                f"Score: {score}/100\n\n"
                f"Sobreextension bajista con MAs alcistas en 1H -- posible reversion."
            )
            return StrategyType.BB_SALIDA_CALL, SignalDirection.CALL, strength, exp
        elif ma.trend_1h in ["bajista_fuerte","bajista_parcial"]:
            exp = (
                f"BB SALIDA BANDA INFERIOR -- Ruptura bajista fuerte -> PUT.\n\n"
                f"BB 15min: precio SALIO de banda inferior -- percentil {bb.bandwidth_pct_15m:.0f}% (ENTRADA)\n"
                f"MAs 1H: {ma.trend_1h} -- tendencia bajista (DECISION)\n"
                f"{sr_txt}{support_txt}"
                f"Diario: {ma.daily_trend} (contexto)\n"
                f"Score: {score}/100\n\n"
                f"Ruptura con MAs bajistas en 1H -- continuacion del movimiento."
            )
            return StrategyType.BB_SALIDA_PUT, SignalDirection.PUT, strength, exp

    return StrategyType.NONE, SignalDirection.NEUTRAL, SignalStrength.DEBIL, ""


def _strategy_bb_acercamiento(ma, bb, score, pan_dir) -> tuple:
    if not bb.is_expanding_15m or bb.bandwidth_pct_15m < 55:
        return StrategyType.NONE, SignalDirection.NEUTRAL, SignalStrength.DEBIL, ""
    if score < 50:
        return StrategyType.NONE, SignalDirection.NEUTRAL, SignalStrength.DEBIL, ""

    sr_txt = f"Rebotando en {ma.bouncing_on}.\n" if ma.bouncing_on else ""

    if bb.price_near_upper_15m and ma.trend_1h in ["bajista_fuerte","bajista_parcial"]:
        exp = (
            f"BB ACERCAMIENTO A BANDA SUPERIOR -- Anticipando PUT.\n\n"
            f"BB 15min: precio acercandose a banda superior -- percentil {bb.bandwidth_pct_15m:.0f}% (ENTRADA)\n"
            f"MAs 1H: {ma.trend_1h} -- bajista (DECISION)\n"
            f"{sr_txt}Diario: {ma.daily_trend} (contexto)\n"
            f"Score: {score}/100\n\n"
            f"Posible PUT si el precio sale de la banda."
        )
        return StrategyType.BB_ACERCAMIENTO_PUT, SignalDirection.PUT, SignalStrength.MODERADO, exp

    elif bb.price_near_lower_15m and ma.trend_1h in ["alcista_fuerte","alcista_parcial"]:
        exp = (
            f"BB ACERCAMIENTO A BANDA INFERIOR -- Anticipando CALL.\n\n"
            f"BB 15min: precio acercandose a banda inferior -- percentil {bb.bandwidth_pct_15m:.0f}% (ENTRADA)\n"
            f"MAs 1H: {ma.trend_1h} -- alcista (DECISION)\n"
            f"{sr_txt}Diario: {ma.daily_trend} (contexto)\n"
            f"Score: {score}/100\n\n"
            f"Posible CALL si el precio sale de la banda."
        )
        return StrategyType.BB_ACERCAMIENTO_CALL, SignalDirection.CALL, SignalStrength.MODERADO, exp

    return StrategyType.NONE, SignalDirection.NEUTRAL, SignalStrength.DEBIL, ""


def _strategy_rebote(ma, bb, score) -> tuple:
    if not bb.is_high_volatility_15m:
        return StrategyType.NONE, SignalDirection.NEUTRAL, SignalStrength.DEBIL, ""

    strength = score_to_strength(score)

    if ma.bounce_dir == "up" and ma.trend_1h in ["alcista_fuerte","alcista_parcial"]:
        exp = (
            f"REBOTE EN {ma.bouncing_on} COMO PISO -> CALL.\n\n"
            f"MAs 1H: {ma.bouncing_on} actuando como PISO -- tendencia {ma.trend_1h} (DECISION)\n"
            f"BB 15min: alta volatilidad {bb.bandwidth_pct_15m:.0f}% -- confirmando (ENTRADA)\n"
            f"Diario: {ma.daily_trend} (contexto)\n"
            f"Score: {score}/100\n\n"
            f"Del libro: las MAs actuan como pisos en tendencia alcista."
        )
        return StrategyType.REBOTE_MA_CALL, SignalDirection.CALL, strength, exp

    elif ma.bounce_dir == "down" and ma.trend_1h in ["bajista_fuerte","bajista_parcial"]:
        exp = (
            f"REBOTE EN {ma.bouncing_on} COMO TECHO -> PUT.\n\n"
            f"MAs 1H: {ma.bouncing_on} actuando como TECHO -- tendencia {ma.trend_1h} (DECISION)\n"
            f"BB 15min: alta volatilidad {bb.bandwidth_pct_15m:.0f}% -- confirmando (ENTRADA)\n"
            f"Diario: {ma.daily_trend} (contexto)\n"
            f"Score: {score}/100\n\n"
            f"Del libro: las MAs actuan como techos en tendencia bajista."
        )
        return StrategyType.REBOTE_MA_PUT, SignalDirection.PUT, strength, exp

    return StrategyType.NONE, SignalDirection.NEUTRAL, SignalStrength.DEBIL, ""


# ============================================================
# RECOMENDACION
# ============================================================

def generate_rec(direction, strength, events, ma, chop) -> str:
    high_today = any(e["impact"] == "alto" and e["days"] == 0 for e in events)
    if chop > 61.8:
        return " NO OPERAR -- Mercado choppy sin direccion."
    if strength == SignalStrength.DEBIL:
        return " No entrar -- senal debil."
    if high_today:
        return f"! {direction.value} {strength.value} -- Evento de alto impacto HOY. Esperar o reducir tamano."
    if direction == SignalDirection.NEUTRAL:
        return " MONITOREAR -- Esperar confirmacion de direccion."
    blind = f"\n! {ma.daily_warning}" if ma.daily_warning else ""
    if strength == SignalStrength.FUERTE:
        return f" {direction.value} FUERTE -- Panorama completo alineado. Confirmar en TC2000.{blind}"
    else:
        return f" {direction.value} MODERADO -- Mayoria alineada. Confirmar visualmente.{blind}"


# ============================================================
# MOTOR PRINCIPAL
# ============================================================

def fetch_data(ticker: str) -> tuple:
    stock = yf.Ticker(ticker)
    return (
        stock.history(period="5d",  interval="15m"),
        stock.history(period="3mo", interval="1h"),
        stock.history(period="1y",  interval="1d")
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
        score, pan_dir = calc_score(ma, bb, gap, chop)

        strategy, direction, strength, explanation = identify_strategy(
            ma, bb, gap, chop, score, pan_dir
        )

        if strength == SignalStrength.DEBIL or strategy == StrategyType.NONE:
            print(f"[{ticker}] -- Sin senal (Score:{score} | Chop:{chop} | BB:{bb.bandwidth_pct_15m:.0f}% | MAs:{ma.trend_1h})")
            return None

        events = check_events()
        rec = generate_rec(direction, strength, events, ma, chop)

        warns = [e["warning"] for e in events]
        if ma.daily_warning: warns.append(ma.daily_warning)
        if bb.bb_contracting_15m: warns.append("! BB 15min contrayendose -- monitorear agotamiento")

        et = pytz.timezone('US/Eastern')
        now = datetime.now(et)

        return Alert(
            ticker=ticker,
            timestamp=now.strftime("%Y-%m-%d %I:%M %p ET"),
            strategy=strategy, direction=direction, strength=strength,
            ma=ma, bb=bb, score=score, price=ma.price,
            explanation=explanation, recommendation=rec,
            warning="\n".join(warns) if warns else None,
            external_events=events
        )

    except Exception as e:
        print(f"[{ticker}] Error: {e}")
        return None


# ============================================================
# TICKERS & RUN
# ============================================================

DEFAULT_TICKERS = [
    "SPY", "QQQ", "DIA", "IWM", "GLD", "TLT", "USO",
    "^GSPC",
    "AAPL", "TSLA", "NVDA", "MSFT", "META", "AMZN",
    "AMD", "MU", "MRNA", "NIO", "LI"
]


def run_analysis(tickers: list = None) -> list:
    if tickers is None:
        import os
        env = os.environ.get("SAAI_TICKERS", "")
        tickers = [t.strip() for t in env.split(",")] if env else DEFAULT_TICKERS

    et = pytz.timezone('US/Eastern')
    print(f"\n{'='*65}")
    print(f"   SAAI v4 -- Smart Alert AI System")
    print(f"   Un Millon al Ano No Hace Dano -- Yoel Sardinas")
    print(f"   MAs: Decision en 1H | Diario: Puntos ciegos")
    print(f"    BB: Decision en 15min | La puerta de entrada")
    print(f"   Score < 50 = no alerta | 50-60 = MODERADO | > 60 = FUERTE")
    print(f"   {len(tickers)} tickers | {datetime.now(et).strftime('%I:%M %p ET')}")
    print(f"{'='*65}\n")

    alerts = []
    for ticker in tickers:
        print(f"[{ticker}] Analizando...")
        a = analyze_ticker(ticker)
        if a:
            alerts.append(a)
            print(f"[{ticker}]  {a.strategy.value} -> {a.direction.value} {a.strength.value} (Score:{a.score})")

    print(f"\n{'='*65}")
    print(f"  Analizados: {len(tickers)} | Alertas: {len(alerts)}")
    print(f"  'Si algun elemento no se presenta, se convierte en una apuesta.'")
    print(f"{'='*65}\n")

    return alerts


if __name__ == "__main__":
    alerts = run_analysis()
    for a in alerts:
        print(f"\n{''*55}")
        print(f" {a.ticker} -- {a.timestamp} -- ${a.price}")
        print(f" {a.strategy.value}")
        print(f" {a.direction.value} {a.strength.value} | Score: {a.score}/100")
        print(f"MAs 1H: {a.ma.trend_1h} | BB 15min: {a.bb.bandwidth_pct_15m:.0f}% | Diario: {a.ma.daily_trend}")
        if a.ma.daily_warning: print(f"\n{a.ma.daily_warning}")
        print(f"\n{a.explanation}")
        if a.warning: print(f"\n{a.warning}")
        print(f"\n{a.recommendation}")
        print(f"{''*55}")
