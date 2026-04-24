"""
SAAI — Smart Alert AI System
Motor de Análisis Técnico basado en "Un Millón al Año No Hace Daño" — Yoel Sardiñas

Este módulo implementa las 3 estrategias del libro:
  - Estrategia 1: Cambio de tendencia lateral al alza (CALL)
  - Estrategia 2: Cambio de tendencia lateral a la baja (PUT)
  - Estrategia 3: Saltos en apertura

Las 6 capas de análisis:
  1. Tendencia Mayor (MAs en 1H y Diario)
  2. Pisos y Techos Dinámicos (rebotes en MAs)
  3. Bollinger Bands 15min (volatilidad)
  4. Estrategia del Libro identificada
  5. Eventos Externos (FOMC, CPI, OpEx, Earnings)
  6. Calidad y Fuerza de la Señal
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass, field
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
    CANAL_LATERAL_ALZA = "Estrategia 1 — Canal Lateral al Alza"
    CANAL_LATERAL_BAJA = "Estrategia 2 — Canal Lateral a la Baja"
    SALTO_ALCISTA = "Estrategia 3 — Salto Alcista"
    SALTO_BAJISTA = "Estrategia 3 — Salto Bajista"
    REBOTE_MA_ALCISTA = "Rebote en MA — Soporte Respetado"
    REBOTE_MA_BAJISTA = "Rebote en MA — Resistencia Respetada"
    BB_EXPANSION_ALCISTA = "BB Apertura Volatilidad Alcista"
    BB_EXPANSION_BAJISTA = "BB Apertura Volatilidad Bajista"
    SQUEEZE = "Squeeze — Explosión Inminente"
    NONE = "Sin estrategia identificada"

@dataclass
class MAAnalysis:
    """Capa 1 — Análisis de Medias Móviles"""
    ma20: float
    ma40: float
    ma100: float
    ma200: float
    price: float
    trend: str  # "alcista_fuerte", "alcista_parcial", "bajista_fuerte", "bajista_parcial", "lateral"
    bullish_points: int  # 0-3 cuántas relaciones son alcistas
    is_lateral_channel: bool  # MAs entrelazadas 10+ días
    lateral_days: int  # cuántos días lleva lateral
    price_above_all: bool
    price_below_all: bool

@dataclass 
class SupportResistanceAnalysis:
    """Capa 2 — Pisos y Techos Dinámicos"""
    bouncing_on_ma: Optional[str]  # "MA20", "MA40", "MA100", "MA200" o None
    bounce_direction: str  # "up" (piso) o "down" (techo)
    ma_acting_as: str  # "soporte" o "resistencia"
    distance_to_nearest_ma: float
    nearest_ma: str

@dataclass
class BBAnalysis:
    """Capa 3 — Bollinger Bands 15min"""
    upper_band: float
    lower_band: float
    mid_band: float
    bandwidth: float
    prev_bandwidth: float
    is_expanding: bool
    is_squeeze: bool
    price_above_upper: bool
    price_below_lower: bool
    expansion_pct: float  # % de expansión vs barra anterior

@dataclass
class GapAnalysis:
    """Capa 4 (Saltos) — Análisis de gaps en apertura"""
    has_gap: bool
    gap_direction: str  # "up", "down", "none"
    gap_size: float  # en dólares
    gap_pct: float  # en porcentaje
    is_first_gap: bool  # primer salto en nueva tendencia
    is_reversal_gap: bool  # salto contrario a tendencia dominante

@dataclass
class ExternalEvent:
    """Capa 5 — Eventos Externos"""
    name: str
    date: str
    impact: str  # "alto", "medio", "bajo"
    warning_message: str

@dataclass
class Alert:
    """Alerta final generada por el sistema"""
    ticker: str
    timestamp: str
    strategy: StrategyType
    direction: SignalDirection
    strength: SignalStrength
    ma_analysis: MAAnalysis
    sr_analysis: SupportResistanceAnalysis
    bb_analysis: BBAnalysis
    gap_analysis: Optional[GapAnalysis]
    external_events: list
    price: float
    explanation: str  # Explicación en lenguaje del libro
    recommendation: str
    warning: Optional[str]


# ============================================================
# CAPA 1 — TENDENCIA MAYOR (MAs 1H)
# ============================================================

def analyze_moving_averages(df_1h: pd.DataFrame) -> MAAnalysis:
    """
    Analiza las 4 MAs en temporalidad 1H.
    Determina tendencia, lateralidad y relación con el precio.
    
    Del libro: "Las cuatro medias móviles 20, 40, 100 y 200 periodos deben mostrarse
    de manera lateral o entrelazadas entre ellas dentro de ese canal lateral"
    """
    close = df_1h['Close'].iloc[-1]
    
    ma20 = df_1h['Close'].rolling(20).mean().iloc[-1]
    ma40 = df_1h['Close'].rolling(40).mean().iloc[-1]
    ma100 = df_1h['Close'].rolling(100).mean().iloc[-1]
    ma200 = df_1h['Close'].rolling(200).mean().iloc[-1]
    
    # Contar puntos alcistas (cuántas relaciones MA corta > MA larga)
    bullish_points = 0
    if ma20 > ma40: bullish_points += 1
    if ma40 > ma100: bullish_points += 1
    if ma100 > ma200: bullish_points += 1
    
    # Determinar tendencia
    if bullish_points == 3:
        trend = "alcista_fuerte"
    elif bullish_points == 2:
        trend = "alcista_parcial"
    elif bullish_points == 0:
        trend = "bajista_fuerte"
    elif bullish_points == 1:
        trend = "bajista_parcial"
    else:
        trend = "lateral"
    
    # Detectar canal lateral — MAs entrelazadas
    # Del libro: "10 días o más" con MAs laterales
    is_lateral, lateral_days = detect_lateral_channel(df_1h)
    
    price_above_all = close > max(ma20, ma40, ma100, ma200)
    price_below_all = close < min(ma20, ma40, ma100, ma200)
    
    return MAAnalysis(
        ma20=round(ma20, 2),
        ma40=round(ma40, 2),
        ma100=round(ma100, 2),
        ma200=round(ma200, 2),
        price=round(close, 2),
        trend=trend,
        bullish_points=bullish_points,
        is_lateral_channel=is_lateral,
        lateral_days=lateral_days,
        price_above_all=price_above_all,
        price_below_all=price_below_all
    )


def detect_lateral_channel(df_1h: pd.DataFrame, min_days: int = 10) -> tuple:
    """
    Detecta si las MAs han estado entrelazadas/laterales por 10+ días.
    
    Del libro: "El tiempo en el que el precio debe permanecer dentro de este canal,
    tiene que ser de 10 días o más (podría llegar a ser de más de 30 días)"
    """
    ma20 = df_1h['Close'].rolling(20).mean()
    ma40 = df_1h['Close'].rolling(40).mean()
    ma100 = df_1h['Close'].rolling(100).mean()
    ma200 = df_1h['Close'].rolling(200).mean()
    
    # Calcular spread entre MAs como % del precio
    # Si las MAs están dentro de un rango estrecho, es canal lateral
    lateral_count = 0
    bars_per_day = 7  # ~7 barras de 1H por día de mercado
    
    for i in range(-1, -len(df_1h), -1):
        try:
            mas = [ma20.iloc[i], ma40.iloc[i], ma100.iloc[i], ma200.iloc[i]]
            if any(pd.isna(m) for m in mas):
                break
            ma_range = max(mas) - min(mas)
            price = df_1h['Close'].iloc[i]
            spread_pct = (ma_range / price) * 100
            
            # Si spread < 3% consideramos lateral
            if spread_pct < 3.0:
                lateral_count += 1
            else:
                break
        except (IndexError, KeyError):
            break
    
    lateral_days = lateral_count // bars_per_day
    is_lateral = lateral_days >= min_days
    
    return is_lateral, lateral_days


# ============================================================
# CAPA 2 — PISOS Y TECHOS DINÁMICOS
# ============================================================

def analyze_support_resistance(df_1h: pd.DataFrame, ma_analysis: MAAnalysis) -> SupportResistanceAnalysis:
    """
    Analiza si el precio está rebotando en alguna MA.
    
    Del libro: Las MAs actúan como soporte (piso) en tendencia alcista
    y como resistencia (techo) en tendencia bajista.
    
    MA 20 → piso/techo inmediato
    MA 40 → siguiente nivel
    MA 100 → soporte/resistencia fuerte
    MA 200 → nivel institucional
    """
    close = ma_analysis.price
    ma_levels = {
        "MA20": ma_analysis.ma20,
        "MA40": ma_analysis.ma40,
        "MA100": ma_analysis.ma100,
        "MA200": ma_analysis.ma200
    }
    
    # Encontrar la MA más cercana al precio
    distances = {name: abs(close - val) for name, val in ma_levels.items()}
    nearest_ma = min(distances, key=distances.get)
    nearest_distance = distances[nearest_ma]
    distance_pct = (nearest_distance / close) * 100
    
    # Detectar rebote — precio cerca de MA (dentro de 0.5%) y moviéndose away
    bouncing_on = None
    bounce_dir = "none"
    ma_role = "neutral"
    
    # Revisar las últimas 3 barras para detectar rebote
    if len(df_1h) >= 3:
        recent_closes = df_1h['Close'].iloc[-3:].values
        recent_lows = df_1h['Low'].iloc[-3:].values
        recent_highs = df_1h['High'].iloc[-3:].values
        
        for ma_name, ma_val in ma_levels.items():
            # Rebote al alza (piso) — precio tocó MA desde arriba y rebotó
            if any(abs(low - ma_val) / ma_val < 0.005 for low in recent_lows):
                if close > ma_val:
                    bouncing_on = ma_name
                    bounce_dir = "up"
                    ma_role = "soporte"
                    break
            
            # Rebote a la baja (techo) — precio tocó MA desde abajo y rebotó
            if any(abs(high - ma_val) / ma_val < 0.005 for high in recent_highs):
                if close < ma_val:
                    bouncing_on = ma_name
                    bounce_dir = "down"
                    ma_role = "resistencia"
                    break
    
    return SupportResistanceAnalysis(
        bouncing_on_ma=bouncing_on,
        bounce_direction=bounce_dir,
        ma_acting_as=ma_role,
        distance_to_nearest_ma=round(distance_pct, 3),
        nearest_ma=nearest_ma
    )


# ============================================================
# CAPA 3 — BOLLINGER BANDS 15min
# ============================================================

def analyze_bollinger_bands(df_15m: pd.DataFrame, length: int = 20, num_std: float = 2.0) -> BBAnalysis:
    """
    Analiza Bollinger Bands en temporalidad 15min.
    
    Del libro: "Esa confirmación debe presentarse en Bollinger Bands en periodo de 15
    minutos con alta volatilidad"
    """
    close = df_15m['Close']
    current_close = close.iloc[-1]
    
    # Calcular BB
    sma = close.rolling(length).mean()
    std = close.rolling(length).std()
    
    upper = sma + num_std * std
    lower = sma - num_std * std
    
    current_upper = upper.iloc[-1]
    current_lower = lower.iloc[-1]
    current_mid = sma.iloc[-1]
    
    # Bandwidth actual y anterior
    bandwidth = (current_upper - current_lower) / current_mid
    prev_bandwidth = ((upper.iloc[-2] - lower.iloc[-2]) / sma.iloc[-2]) if len(upper) > 1 else bandwidth
    
    # ¿Está expandiendo?
    is_expanding = bandwidth > prev_bandwidth * 1.05
    expansion_pct = ((bandwidth - prev_bandwidth) / prev_bandwidth * 100) if prev_bandwidth > 0 else 0
    
    # ¿Hay squeeze?
    avg_bandwidth = ((upper - lower) / sma).rolling(20).mean().iloc[-1]
    is_squeeze = bandwidth < avg_bandwidth * 0.75
    
    # ¿Precio fuera de bandas?
    price_above = current_close > current_upper
    price_below = current_close < current_lower
    
    return BBAnalysis(
        upper_band=round(current_upper, 2),
        lower_band=round(current_lower, 2),
        mid_band=round(current_mid, 2),
        bandwidth=round(bandwidth, 6),
        prev_bandwidth=round(prev_bandwidth, 6),
        is_expanding=is_expanding,
        is_squeeze=is_squeeze,
        price_above_upper=price_above,
        price_below_lower=price_below,
        expansion_pct=round(expansion_pct, 2)
    )


# ============================================================
# CAPA 4 — ESTRATEGIA 3: SALTOS (GAPS)
# ============================================================

def analyze_gaps(df_daily: pd.DataFrame, ma_analysis: MAAnalysis) -> GapAnalysis:
    """
    Detecta saltos (gaps) en la apertura del mercado.
    
    Del libro: "Un salto solo puede ocurrir en la apertura del mercado de un día a otro."
    
    Reglas del libro:
    1. Primer salto al finalizar tendencia → 90% continúa dirección del salto
    2. Si día cierra en dirección del salto → 90% segundo salto al día siguiente
    3. Salto contrario a tendencia → posible cambio de tendencia
    4. Salto que se revierte al cierre → inminente cambio de tendencia
    """
    if len(df_daily) < 2:
        return GapAnalysis(False, "none", 0, 0, False, False)
    
    today_open = df_daily['Open'].iloc[-1]
    yesterday_close = df_daily['Close'].iloc[-2]
    
    gap_size = today_open - yesterday_close
    gap_pct = (gap_size / yesterday_close) * 100
    
    # ¿Es un gap significativo? (> 0.3% para ETFs)
    has_gap = abs(gap_pct) > 0.3
    
    if not has_gap:
        return GapAnalysis(False, "none", 0, 0, False, False)
    
    gap_direction = "up" if gap_size > 0 else "down"
    
    # ¿Es primer salto en nueva tendencia?
    # Verificar si la tendencia de MAs es opuesta al gap (posible cambio)
    is_first = False
    is_reversal = False
    
    if gap_direction == "up" and ma_analysis.trend in ["bajista_fuerte", "bajista_parcial"]:
        is_first = True  # Gap alcista en tendencia bajista = posible cambio
    elif gap_direction == "down" and ma_analysis.trend in ["alcista_fuerte", "alcista_parcial"]:
        is_first = True  # Gap bajista en tendencia alcista = posible cambio
    
    # ¿Es salto contrario a tendencia dominante?
    if gap_direction == "up" and ma_analysis.trend in ["bajista_fuerte", "bajista_parcial"]:
        is_reversal = True
    elif gap_direction == "down" and ma_analysis.trend in ["alcista_fuerte", "alcista_parcial"]:
        is_reversal = True
    
    return GapAnalysis(
        has_gap=has_gap,
        gap_direction=gap_direction,
        gap_size=round(abs(gap_size), 2),
        gap_pct=round(abs(gap_pct), 3),
        is_first_gap=is_first,
        is_reversal_gap=is_reversal
    )


# ============================================================
# CAPA 5 — EVENTOS EXTERNOS PREDECIBLES
# ============================================================

# Calendario económico 2026 — actualizar mensualmente
ECONOMIC_CALENDAR = {
    # FOMC Meetings 2026 (fechas estimadas)
    "2026-01-28": {"name": "FOMC Decision", "impact": "alto"},
    "2026-03-18": {"name": "FOMC Decision", "impact": "alto"},
    "2026-05-06": {"name": "FOMC Decision", "impact": "alto"},
    "2026-06-17": {"name": "FOMC Decision", "impact": "alto"},
    "2026-07-29": {"name": "FOMC Decision", "impact": "alto"},
    "2026-09-16": {"name": "FOMC Decision", "impact": "alto"},
    "2026-11-04": {"name": "FOMC Decision", "impact": "alto"},
    "2026-12-16": {"name": "FOMC Decision", "impact": "alto"},
    
    # CPI Dates 2026 (estimadas — segundo martes o miércoles de cada mes)
    "2026-04-14": {"name": "CPI Report", "impact": "alto"},
    "2026-05-13": {"name": "CPI Report", "impact": "alto"},
    "2026-06-10": {"name": "CPI Report", "impact": "alto"},
    "2026-07-15": {"name": "CPI Report", "impact": "alto"},
    
    # Jobs Report (primer viernes de cada mes)
    "2026-05-01": {"name": "Jobs Report (NFP)", "impact": "alto"},
    "2026-06-05": {"name": "Jobs Report (NFP)", "impact": "alto"},
    "2026-07-02": {"name": "Jobs Report (NFP)", "impact": "alto"},
    
    # OpEx — Monthly Options Expiration (tercer viernes de cada mes)
    "2026-04-17": {"name": "OpEx — Vencimiento Opciones Mensual", "impact": "medio"},
    "2026-05-15": {"name": "OpEx — Vencimiento Opciones Mensual", "impact": "medio"},
    "2026-06-19": {"name": "OpEx — Vencimiento Opciones Mensual", "impact": "medio"},
    "2026-07-17": {"name": "OpEx — Vencimiento Opciones Mensual", "impact": "medio"},
}


def check_external_events(date: datetime = None) -> list:
    """
    Verifica si hay eventos económicos hoy o en los próximos 2 días.
    
    Del libro: Las emociones del mercado se amplifican alrededor de eventos macro.
    El sistema debe advertir al trader para que opere con cautela.
    """
    if date is None:
        et = pytz.timezone('US/Eastern')
        date = datetime.now(et)
    
    events = []
    today_str = date.strftime("%Y-%m-%d")
    tomorrow = date + timedelta(days=1)
    day_after = date + timedelta(days=2)
    
    for check_date in [today_str, tomorrow.strftime("%Y-%m-%d"), day_after.strftime("%Y-%m-%d")]:
        if check_date in ECONOMIC_CALENDAR:
            event = ECONOMIC_CALENDAR[check_date]
            is_today = check_date == today_str
            
            if is_today:
                warning = f"⚠️ HOY: {event['name']} — Operar con máxima cautela"
            elif check_date == tomorrow.strftime("%Y-%m-%d"):
                warning = f"📅 MAÑANA: {event['name']} — Considerar reducir tamaño de posición"
            else:
                warning = f"📅 En 2 días: {event['name']} — Tener en cuenta"
            
            events.append(ExternalEvent(
                name=event['name'],
                date=check_date,
                impact=event['impact'],
                warning_message=warning
            ))
    
    return events


# ============================================================
# CAPA 6 — MOTOR DE DECISIÓN (IDENTIFY STRATEGY)
# ============================================================

def identify_strategy(
    ma: MAAnalysis,
    sr: SupportResistanceAnalysis,
    bb: BBAnalysis,
    gap: GapAnalysis
) -> tuple:
    """
    Identifica cuál de las 3 estrategias del libro se está formando.
    
    Retorna: (StrategyType, SignalDirection, SignalStrength, explanation)
    
    Del libro: "Si algún elemento de la estrategia no se está presentando,
    ya no es una estrategia, se convierte en una apuesta."
    """
    
    # ── ESTRATEGIA 3: SALTOS (prioridad más alta — solo en apertura) ──
    if gap.has_gap:
        if gap.gap_direction == "up":
            # Salto alcista
            if ma.trend in ["alcista_fuerte", "alcista_parcial"]:
                # Salto en dirección de tendencia — 90% continúa
                strength = SignalStrength.FUERTE if ma.trend == "alcista_fuerte" else SignalStrength.MODERADO
                explanation = (
                    f"ESTRATEGIA 3 — SALTO ALCISTA en apertura.\n"
                    f"Gap de ${gap.gap_size} ({gap.gap_pct}%) vs cierre anterior.\n"
                    f"MAs en 1H confirman tendencia {ma.trend}.\n"
                    f"Según el libro: 'Cuando ocurre un primer salto, en un alto porcentaje "
                    f"de las veces, el precio continuará en la dirección del salto.'\n"
                    f"Probabilidad según metodología: 90%+ de continuación."
                )
                return StrategyType.SALTO_ALCISTA, SignalDirection.CALL, strength, explanation
            
            elif gap.is_reversal_gap:
                # Salto contrario a tendencia — posible cambio
                explanation = (
                    f"ESTRATEGIA 3 — SALTO ALCISTA CONTRA TENDENCIA.\n"
                    f"Gap de ${gap.gap_size} ({gap.gap_pct}%) — PRIMER salto alcista en tendencia bajista.\n"
                    f"Según el libro: 'Cuando ocurre un salto en dirección contraria, "
                    f"podría indicar que está a punto de ocurrir un cambio de tendencia.'\n"
                    f"⚠️ Monitorear con cautela — esperar confirmación durante el día."
                )
                return StrategyType.SALTO_ALCISTA, SignalDirection.CALL, SignalStrength.MODERADO, explanation
        
        elif gap.gap_direction == "down":
            # Salto bajista
            if ma.trend in ["bajista_fuerte", "bajista_parcial"]:
                strength = SignalStrength.FUERTE if ma.trend == "bajista_fuerte" else SignalStrength.MODERADO
                explanation = (
                    f"ESTRATEGIA 3 — SALTO BAJISTA en apertura.\n"
                    f"Gap de -${gap.gap_size} (-{gap.gap_pct}%) vs cierre anterior.\n"
                    f"MAs en 1H confirman tendencia {ma.trend}.\n"
                    f"Según el libro: 90%+ de probabilidad de continuación bajista."
                )
                return StrategyType.SALTO_BAJISTA, SignalDirection.PUT, strength, explanation
            
            elif gap.is_reversal_gap:
                explanation = (
                    f"ESTRATEGIA 3 — SALTO BAJISTA CONTRA TENDENCIA.\n"
                    f"Gap de -${gap.gap_size} (-{gap.gap_pct}%) — PRIMER salto bajista en tendencia alcista.\n"
                    f"Posible cambio de tendencia según el libro."
                )
                return StrategyType.SALTO_BAJISTA, SignalDirection.PUT, SignalStrength.MODERADO, explanation
    
    # ── ESTRATEGIA 1: CANAL LATERAL AL ALZA ──
    if ma.is_lateral_channel and ma.lateral_days >= 10:
        if bb.is_expanding and bb.price_above_upper:
            # Canal lateral roto al alza con BB confirmando
            strength = SignalStrength.FUERTE if ma.lateral_days >= 15 else SignalStrength.MODERADO
            explanation = (
                f"ESTRATEGIA 1 — CANAL LATERAL AL ALZA.\n"
                f"Las MAs han estado entrelazadas/laterales por {ma.lateral_days} días.\n"
                f"El precio acaba de romper el canal al alza.\n"
                f"BB en 15min confirma con alta volatilidad — bandas expandiendo {bb.expansion_pct}%.\n"
                f"Según el libro: 'Debe presentarse una señal alcista que haga que el precio "
                f"se salga del canal... Esperar confirmación con vela final alcista.'\n"
                f"Rentabilidades históricas del libro: 100% a 3000% en 2-5 días."
            )
            return StrategyType.CANAL_LATERAL_ALZA, SignalDirection.CALL, strength, explanation
        
        elif bb.is_expanding and bb.price_below_lower:
            # Canal lateral roto a la baja con BB confirmando
            strength = SignalStrength.FUERTE if ma.lateral_days >= 15 else SignalStrength.MODERADO
            explanation = (
                f"ESTRATEGIA 2 — CANAL LATERAL A LA BAJA.\n"
                f"Las MAs han estado entrelazadas/laterales por {ma.lateral_days} días.\n"
                f"El precio acaba de romper el canal a la baja.\n"
                f"BB en 15min confirma con alta volatilidad — bandas expandiendo {bb.expansion_pct}%.\n"
                f"Según el libro: 'Debe presentarse una señal bajista que haga que el precio "
                f"se salga del canal... Esperar confirmación con vela final bajista.'\n"
                f"Rentabilidades históricas del libro: 100% a 3000% en 2-5 días."
            )
            return StrategyType.CANAL_LATERAL_BAJA, SignalDirection.PUT, strength, explanation
        
        elif bb.is_squeeze:
            # Canal lateral con squeeze — explosión inminente
            explanation = (
                f"SQUEEZE en canal lateral de {ma.lateral_days} días.\n"
                f"BB muy comprimidas — explosión de volatilidad inminente.\n"
                f"Posible Estrategia 1 o 2 a punto de formarse.\n"
                f"⚠️ ESPERAR confirmación de dirección antes de entrar."
            )
            return StrategyType.SQUEEZE, SignalDirection.NEUTRAL, SignalStrength.MODERADO, explanation
    
    # ── BB EXPANDIENDO CON MAs CONFIRMANDO (sin canal lateral) ──
    if bb.is_expanding:
        if bb.price_above_upper and ma.trend in ["bajista_fuerte", "bajista_parcial"]:
            strength = SignalStrength.FUERTE if ma.trend == "bajista_fuerte" else SignalStrength.MODERADO
            explanation = (
                f"BB abriendo volatilidad al alza en 15min — precio sobre banda superior.\n"
                f"MAs en 1H confirman tendencia {ma.trend}.\n"
            )
            if sr.bouncing_on_ma:
                explanation += f"Precio rebotando en {sr.bouncing_on_ma} como {sr.ma_acting_as}.\n"
            explanation += "Considerar PUT — confluencia de señales bajistas."
            return StrategyType.BB_EXPANSION_BAJISTA, SignalDirection.PUT, strength, explanation
        
        elif bb.price_below_lower and ma.trend in ["alcista_fuerte", "alcista_parcial"]:
            strength = SignalStrength.FUERTE if ma.trend == "alcista_fuerte" else SignalStrength.MODERADO
            explanation = (
                f"BB abriendo volatilidad a la baja en 15min — precio bajo banda inferior.\n"
                f"MAs en 1H confirman tendencia {ma.trend}.\n"
            )
            if sr.bouncing_on_ma:
                explanation += f"Precio rebotando en {sr.bouncing_on_ma} como {sr.ma_acting_as}.\n"
            explanation += "Considerar CALL — confluencia de señales alcistas."
            return StrategyType.BB_EXPANSION_ALCISTA, SignalDirection.CALL, strength, explanation
    
    # ── REBOTE EN MA CON BB CONFIRMANDO ──
    if sr.bouncing_on_ma and bb.is_expanding:
        if sr.bounce_direction == "up" and ma.trend in ["alcista_fuerte", "alcista_parcial"]:
            explanation = (
                f"Precio rebotó en {sr.bouncing_on_ma} como PISO en tendencia alcista.\n"
                f"BB en 15min confirma expansión al alza.\n"
                f"Confluencia: soporte respetado + BB confirmando dirección."
            )
            return StrategyType.REBOTE_MA_ALCISTA, SignalDirection.CALL, SignalStrength.MODERADO, explanation
        
        elif sr.bounce_direction == "down" and ma.trend in ["bajista_fuerte", "bajista_parcial"]:
            explanation = (
                f"Precio rebotó en {sr.bouncing_on_ma} como TECHO en tendencia bajista.\n"
                f"BB en 15min confirma expansión a la baja.\n"
                f"Confluencia: resistencia respetada + BB confirmando dirección."
            )
            return StrategyType.REBOTE_MA_BAJISTA, SignalDirection.PUT, SignalStrength.MODERADO, explanation
    
    # ── SQUEEZE SIN CANAL LATERAL ──
    if bb.is_squeeze:
        explanation = (
            f"Squeeze detectado en BB 15min — bandas muy comprimidas.\n"
            f"Explosión de volatilidad inminente.\n"
            f"Tendencia actual en MAs: {ma.trend}.\n"
            f"⚠️ ESPERAR dirección confirmada antes de entrar."
        )
        return StrategyType.SQUEEZE, SignalDirection.NEUTRAL, SignalStrength.DEBIL, explanation
    
    # ── NADA DETECTADO ──
    return StrategyType.NONE, SignalDirection.NEUTRAL, SignalStrength.DEBIL, ""


# ============================================================
# MOTOR PRINCIPAL — ORQUESTADOR
# ============================================================

def fetch_data(ticker: str) -> tuple:
    """
    Descarga datos de Yahoo Finance para un ticker.
    Retorna: (df_15min, df_1h, df_daily)
    """
    stock = yf.Ticker(ticker)
    
    # 15min — últimos 5 días
    df_15m = stock.history(period="5d", interval="15m")
    
    # 1H — último mes
    df_1h = stock.history(period="1mo", interval="1h")
    
    # Daily — últimos 6 meses (para detectar canales laterales de 30+ días)
    df_daily = stock.history(period="6mo", interval="1d")
    
    return df_15m, df_1h, df_daily


def generate_recommendation(direction: SignalDirection, strength: SignalStrength, events: list) -> str:
    """
    Genera la recomendación final basada en el libro.
    
    Del libro: "Las inversiones son 80% emociones y 20% conocimiento."
    El sistema elimina la emoción y se enfoca en hechos.
    """
    has_high_impact_today = any(e.impact == "alto" and "HOY" in e.warning_message for e in events)
    
    if strength == SignalStrength.DEBIL:
        return "❌ No entrar — señal débil. Esperar condiciones mejores."
    
    if has_high_impact_today:
        return f"⚠️ {direction.value} {strength.value} — Pero hay evento de alto impacto HOY. Esperar después del evento o reducir tamaño significativamente."
    
    if direction == SignalDirection.NEUTRAL:
        return "👀 MONITOREAR — Esperar confirmación de dirección antes de entrar."
    
    if strength == SignalStrength.FUERTE:
        return f"📍 {direction.value} FUERTE — Panorama completo alineado. Confirmar en TC2000 y tomar acción."
    else:
        return f"📍 {direction.value} MODERADO — Mayoría de señales alineadas. Confirmar visualmente antes de entrar."


def analyze_ticker(ticker: str) -> Optional[Alert]:
    """
    Análisis completo de un ticker — ejecuta las 6 capas.
    Solo retorna alerta si la señal es FUERTE o MODERADA.
    
    Principio del libro: "Si algún elemento no se presenta, se convierte en una apuesta."
    """
    try:
        # Descargar datos
        df_15m, df_1h, df_daily = fetch_data(ticker)
        
        if df_15m.empty or df_1h.empty or df_daily.empty:
            print(f"[{ticker}] Sin datos disponibles")
            return None
        
        # Capa 1 — Tendencia Mayor
        ma = analyze_moving_averages(df_1h)
        
        # Capa 2 — Pisos y Techos
        sr = analyze_support_resistance(df_1h, ma)
        
        # Capa 3 — Bollinger Bands 15min
        bb = analyze_bollinger_bands(df_15m)
        
        # Capa 4 — Saltos
        gap = analyze_gaps(df_daily, ma)
        
        # Capa 5 — Eventos Externos
        events = check_external_events()
        
        # Capa 6 — Identificar estrategia
        strategy, direction, strength, explanation = identify_strategy(ma, sr, bb, gap)
        
        # Solo alertar si es FUERTE o MODERADO
        if strength == SignalStrength.DEBIL:
            print(f"[{ticker}] Señal débil — no se genera alerta")
            return None
        
        if strategy == StrategyType.NONE:
            print(f"[{ticker}] Sin estrategia identificada")
            return None
        
        # Generar recomendación
        recommendation = generate_recommendation(direction, strength, events)
        
        # Generar warning si hay eventos
        warning = None
        if events:
            warning = "\n".join([e.warning_message for e in events])
        
        # Timestamp
        et = pytz.timezone('US/Eastern')
        now = datetime.now(et)
        
        alert = Alert(
            ticker=ticker,
            timestamp=now.strftime("%Y-%m-%d %I:%M %p ET"),
            strategy=strategy,
            direction=direction,
            strength=strength,
            ma_analysis=ma,
            sr_analysis=sr,
            bb_analysis=bb,
            gap_analysis=gap,
            external_events=events,
            price=ma.price,
            explanation=explanation,
            recommendation=recommendation,
            warning=warning
        )
        
        return alert
        
    except Exception as e:
        print(f"[{ticker}] Error en análisis: {e}")
        return None


def run_analysis(tickers: list = None) -> list:
    """
    Ejecuta análisis completo para todos los tickers.
    Default: SPY, QQQ, DIA
    """
    if tickers is None:
        tickers = ["SPY", "QQQ", "DIA"]
    
    print(f"\n{'='*60}")
    print(f"  SAAI — Smart Alert AI System")
    print(f"  Metodología: Un Millón al Año No Hace Daño")
    print(f"  Tickers: {', '.join(tickers)}")
    et = pytz.timezone('US/Eastern')
    print(f"  Hora: {datetime.now(et).strftime('%Y-%m-%d %I:%M %p ET')}")
    print(f"{'='*60}\n")
    
    alerts = []
    
    for ticker in tickers:
        print(f"[{ticker}] Analizando...")
        alert = analyze_ticker(ticker)
        if alert:
            alerts.append(alert)
            print(f"[{ticker}] ✅ ALERTA: {alert.strategy.value} → {alert.direction.value} {alert.strength.value}")
        else:
            print(f"[{ticker}] — Sin señal")
    
    print(f"\n{'='*60}")
    print(f"  Total alertas generadas: {len(alerts)}")
    print(f"{'='*60}\n")
    
    return alerts


if __name__ == "__main__":
    alerts = run_analysis()
    for alert in alerts:
        print(f"\n{'─'*50}")
        print(f"📊 {alert.ticker} — {alert.timestamp}")
        print(f"📍 {alert.strategy.value}")
        print(f"🎯 {alert.direction.value} {alert.strength.value}")
        print(f"\n{alert.explanation}")
        if alert.warning:
            print(f"\n{alert.warning}")
        print(f"\n{alert.recommendation}")
        print(f"{'─'*50}")
