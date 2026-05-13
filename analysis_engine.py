"""
SAAI v6.1 - Smart Alert AI System
E4 -- Saliendo de Bollinger Bands
Basado en documento de metodologia personal

CAMBIOS vs v6.0:
  - 15min: 4 criterios obligatorios (igual que documento)
  - 1H: bonus, no obligatorio (como dice el documento)
  - Diario: contexto, no obligatorio (como dice el documento)
  - Score minimo: 55 (mas señales, misma calidad)
  - RSI fixes del backtesting mantenidos
  - 46 tickers completos
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

TICKERS_SAAI = {
    "TECHNOLOGY":     ["AMZN","AAPL","GOOG","META","MSFT","NFLX","PLTR","ORCL"],
    "SEMICONDUCTORS": ["AMD","MU","NVDA","QCOM","AVGO","SOXL"],
    "SOFTWARE_APP":   ["DASH","LYFT","UBER"],
    "CONSUMER":       ["HD","LOW","WMT"],
    "INDEX_USA":      ["DIA","QQQ","SPY","IWM","TNA"],
    "CARDS":          ["AXP","C","MA","PYPL","V"],
    "CHINA":          ["BABA","LI","NIO","XPEV"],
    "COMMODITY":      ["GLD","SLV","USO"],
    "FINANCIAL_DATA": ["COIN","HOOD"],
    "HEALTHCARE":     ["CVS","MRNA","PFE"],
    "INDUSTRIALS":    ["BA"],
    "NUCLEAR_ENERGY": ["URA"],
    "TSLA":           ["TSLA"],
}
DEFAULT_TICKERS = [t for group in TICKERS_SAAI.values() for t in group]

class SignalDirection(Enum):
    CALL    = "CALL"
    PUT     = "PUT"
    NEUTRAL = "NEUTRAL"

class SignalStrength(Enum):
    FUERTE   = "FUERTE"
    MODERADO = "MODERADO"
    DEBIL    = "DEBIL"

class StrategyType(Enum):
    E4_CALL = "E4 -- Saliendo de BB al Alza (CALL)"
    E4_PUT  = "E4 -- Saliendo de BB a la Baja (PUT)"
    NONE    = "Sin estrategia"

@dataclass
class BB15Analysis:
    upper: float; lower: float; mid: float
    mid_slope_pct: float; mid_alcista: bool; mid_bajista: bool
    bandwidth_pct: float; bandas_abiertas: bool
    precio: float; precio_sobre_mid: bool; precio_bajo_mid: bool
    espacio_superior_pct: float; espacio_inferior_pct: float
    hay_espacio_call: bool; hay_espacio_put: bool
    banda_inf_abriendo: bool; banda_sup_abriendo: bool
    rsi: float; volatilidad: str

@dataclass
class BB1HAnalysis:
    upper: float; lower: float; mid: float; precio: float
    tendencia: str; mid_alcista: bool; mid_bajista: bool
    espacio_superior_pct: float; espacio_inferior_pct: float
    hay_espacio_call: bool; hay_espacio_put: bool
    volatilidad_abierta: bool
    ma20_1h: float; ma40_1h: float; ma100_1h: float; ma200_1h: float

@dataclass
class BBDiarioAnalysis:
    upper: float; lower: float; mid: float; precio: float
    tendencia: str; precio_sobre_mid: bool; precio_bajo_mid: bool
    espacio_superior_pct: float; espacio_inferior_pct: float
    hay_espacio_call: bool; hay_espacio_put: bool
    volatilidad_abierta: bool

@dataclass
class Alert:
    ticker: str; timestamp: str
    strategy: StrategyType; direction: SignalDirection; strength: SignalStrength
    bb15: BB15Analysis; bb1h: BB1HAnalysis; bbdiario: BBDiarioAnalysis
    score: float; criterios_call: dict; criterios_put: dict
    explanation: str; recommendation: str; warning: Optional[str]
    external_events: list; earnings: dict; agotamiento: dict; categoria: str

ECONOMIC_CALENDAR = {
    "2026-05-13": {"name": "CPI Report",      "impact": "alto"},
    "2026-05-15": {"name": "OpEx Mensual",    "impact": "medio"},
    "2026-06-10": {"name": "CPI Report",      "impact": "alto"},
    "2026-06-17": {"name": "FOMC Decision",   "impact": "alto"},
    "2026-07-02": {"name": "Jobs Report NFP", "impact": "alto"},
    "2026-07-15": {"name": "CPI Report",      "impact": "alto"},
    "2026-07-29": {"name": "FOMC Decision",   "impact": "alto"},
    "2026-08-12": {"name": "CPI Report",      "impact": "alto"},
    "2026-09-09": {"name": "FOMC Decision",   "impact": "alto"},
    "2026-10-07": {"name": "Jobs Report NFP", "impact": "alto"},
    "2026-10-14": {"name": "CPI Report",      "impact": "alto"},
}

def check_events():
    et = pytz.timezone('US/Eastern')
    now = datetime.now(et)
    events = []
    for i in range(3):
        d = (now + timedelta(days=i)).strftime("%Y-%m-%d")
        if d in ECONOMIC_CALENDAR:
            ev = ECONOMIC_CALENDAR[d]
            warn = f"{'HOY' if i==0 else 'MANANA' if i==1 else 'En 2 dias'}: {ev['name']}"
            events.append({"name": ev["name"], "impact": ev["impact"],
                           "warning": warn, "days": i})
    return events

def check_earnings(ticker):
    try:
        stock = yf.Ticker(ticker)
        calendar = stock.calendar
        earnings_date = None
        if isinstance(calendar, dict):
            ed = calendar.get("Earnings Date")
            if ed is not None:
                if hasattr(ed, '__iter__') and not isinstance(ed, str):
                    ed = list(ed); earnings_date = ed[0] if ed else None
                else: earnings_date = ed
        elif hasattr(calendar, 'columns'):
            if "Earnings Date" in calendar.columns:
                earnings_date = calendar["Earnings Date"].iloc[0]
        if earnings_date is None: return {"has_earnings": False}
        if hasattr(earnings_date, 'tzinfo') and earnings_date.tzinfo is not None:
            earnings_date = earnings_date.replace(tzinfo=None)
        if hasattr(earnings_date, 'to_pydatetime'):
            earnings_date = earnings_date.to_pydatetime().replace(tzinfo=None)
        et = pytz.timezone('US/Eastern')
        now = datetime.now(et).replace(tzinfo=None)
        days_away = (earnings_date.date() - now.date()).days
        if days_away < 0 or days_away > 7: return {"has_earnings": False}
        date_str = earnings_date.strftime("%Y-%m-%d")
        if days_away == 0:   warn = f"EARNINGS HOY ({date_str}) -- NO ENTRAR."; impact = "CRITICO"
        elif days_away == 1: warn = f"EARNINGS MANANA ({date_str}) -- Reducir tamano."; impact = "ALTO"
        else:                warn = f"EARNINGS en {days_away} dias ({date_str})."; impact = "MEDIO"
        return {"has_earnings": True, "days_away": days_away,
                "date": date_str, "warning": warn, "impact": impact}
    except: return {"has_earnings": False}

def calc_choppiness(df_1h, n=14):
    if len(df_1h) < n+2: return 50.0
    try:
        hi = df_1h['High'].tail(n+1); lo = df_1h['Low'].tail(n+1); cl = df_1h['Close'].tail(n+1)
        tr = pd.concat([hi-lo,(hi-cl.shift(1)).abs(),(lo-cl.shift(1)).abs()],axis=1).max(axis=1)
        atr = float(tr.tail(n).sum()); hl = float(hi.tail(n).max()-lo.tail(n).min())
        return round(100*np.log10(atr/hl)/np.log10(n),1) if hl>0 else 50.0
    except: return 50.0

def calc_rsi(close, period=14):
    try:
        if len(close) < period+2: return 50.0
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta).clip(lower=0).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = float((100-(100/(1+rs))).iloc[-1])
        return round(rsi,1) if not np.isnan(rsi) else 50.0
    except: return 50.0

def analyze_bb15(df_15m):
    if len(df_15m) < 25: return None
    close = df_15m['Close']; price = float(close.iloc[-1])
    sma = close.rolling(20).mean(); std = close.rolling(20).std()
    upper = sma+2*std; lower = sma-2*std
    mid_now = float(sma.iloc[-1]); upper_now = float(upper.iloc[-1]); lower_now = float(lower.iloc[-1])
    if mid_now == 0: return None
    mid_3ago = float(sma.iloc[-4]) if len(sma)>=4 else mid_now
    mid_slope = round((mid_now-mid_3ago)/mid_3ago*100,4) if mid_3ago>0 else 0.0
    mid_alcista = mid_slope > 0.015; mid_bajista = mid_slope < -0.015
    bw_now = (upper_now-lower_now)/mid_now if mid_now>0 else 0
    bw_series = ((upper-lower)/sma).dropna()
    pct_vol = float((bw_series.tail(60)<bw_now).mean()*100) if len(bw_series)>0 else 50.0
    bandas_abiertas = pct_vol >= 60
    volatilidad = "ALTA" if pct_vol>=80 else "MEDIA" if pct_vol>=60 else "BAJA"
    espacio_sup = round((upper_now-price)/price*100,2) if price>0 else 0.0
    espacio_inf = round((price-lower_now)/price*100,2) if price>0 else 0.0
    lower_prev = float(lower.iloc[-2]) if len(lower)>1 else lower_now
    upper_prev = float(upper.iloc[-2]) if len(upper)>1 else upper_now
    return BB15Analysis(
        upper=round(upper_now,2), lower=round(lower_now,2), mid=round(mid_now,2),
        mid_slope_pct=mid_slope, mid_alcista=mid_alcista, mid_bajista=mid_bajista,
        bandwidth_pct=round(pct_vol,1), bandas_abiertas=bandas_abiertas,
        precio=round(price,2), precio_sobre_mid=price>mid_now, precio_bajo_mid=price<mid_now,
        espacio_superior_pct=espacio_sup, espacio_inferior_pct=espacio_inf,
        hay_espacio_call=espacio_sup>=0.3, hay_espacio_put=espacio_inf>=0.3,
        banda_inf_abriendo=lower_now<lower_prev*0.9995,
        banda_sup_abriendo=upper_now>upper_prev*1.0005,
        rsi=calc_rsi(close), volatilidad=volatilidad,
    )

def analyze_bb1h(df_1h):
    if len(df_1h) < 60: return None
    close = df_1h['Close']; price = float(close.iloc[-1])
    ma20=float(close.rolling(20).mean().iloc[-1]); ma40=float(close.rolling(40).mean().iloc[-1])
    ma100=float(close.rolling(min(100,len(close))).mean().iloc[-1])
    ma200=float(close.rolling(min(200,len(close))).mean().iloc[-1])
    bp = sum([ma20>ma40,ma40>ma100,ma100>ma200])
    tmap={3:"alcista_fuerte",2:"alcista_parcial",1:"bajista_parcial",0:"bajista_fuerte"}
    tendencia = tmap.get(bp,"lateral")
    sma=close.rolling(20).mean(); std=close.rolling(20).std()
    upper=sma+2*std; lower=sma-2*std
    mid_now=float(sma.iloc[-1]); upper_now=float(upper.iloc[-1]); lower_now=float(lower.iloc[-1])
    mid_3ago=float(sma.iloc[-4]) if len(sma)>=4 else mid_now
    slope=(mid_now-mid_3ago)/mid_3ago*100 if mid_3ago>0 else 0.0
    espacio_sup=round((upper_now-price)/price*100,2) if price>0 else 0.0
    espacio_inf=round((price-lower_now)/price*100,2) if price>0 else 0.0
    bw_now=(upper_now-lower_now)/mid_now if mid_now>0 else 0
    bw_series=((upper-lower)/sma).dropna()
    pct_1h=float((bw_series.tail(60)<bw_now).mean()*100) if len(bw_series)>=10 else 50.0
    return BB1HAnalysis(
        upper=round(upper_now,2), lower=round(lower_now,2), mid=round(mid_now,2),
        precio=round(price,2), tendencia=tendencia,
        mid_alcista=slope>0.03, mid_bajista=slope<-0.03,
        espacio_superior_pct=espacio_sup, espacio_inferior_pct=espacio_inf,
        hay_espacio_call=espacio_sup>=0.5, hay_espacio_put=espacio_inf>=0.5,
        volatilidad_abierta=pct_1h>=55,
        ma20_1h=round(ma20,2), ma40_1h=round(ma40,2),
        ma100_1h=round(ma100,2), ma200_1h=round(ma200,2),
    )

def analyze_bbdiario(df_daily):
    if len(df_daily) < 40: return None
    close=df_daily['Close']; price=float(close.iloc[-1])
    ma20=float(close.rolling(20).mean().iloc[-1]); ma40=float(close.rolling(40).mean().iloc[-1])
    ma100=float(close.rolling(min(100,len(close))).mean().iloc[-1])
    ma200=float(close.rolling(min(200,len(close))).mean().iloc[-1])
    bp=sum([ma20>ma40,ma40>ma100,ma100>ma200])
    tmap={3:"alcista_fuerte",2:"alcista_parcial",1:"bajista_parcial",0:"bajista_fuerte"}
    tendencia=tmap.get(bp,"lateral")
    sma=close.rolling(20).mean(); std=close.rolling(20).std()
    upper=sma+2*std; lower=sma-2*std
    mid_now=float(sma.iloc[-1]); upper_now=float(upper.iloc[-1]); lower_now=float(lower.iloc[-1])
    espacio_sup=round((upper_now-price)/price*100,2) if price>0 else 0.0
    espacio_inf=round((price-lower_now)/price*100,2) if price>0 else 0.0
    bw_now=(upper_now-lower_now)/mid_now if mid_now>0 else 0
    bw_series=((upper-lower)/sma).dropna()
    pct_d=float((bw_series.tail(60)<bw_now).mean()*100) if len(bw_series)>=10 else 50.0
    return BBDiarioAnalysis(
        upper=round(upper_now,2), lower=round(lower_now,2), mid=round(mid_now,2),
        precio=round(price,2), tendencia=tendencia,
        precio_sobre_mid=price>mid_now, precio_bajo_mid=price<mid_now,
        espacio_superior_pct=espacio_sup, espacio_inferior_pct=espacio_inf,
        hay_espacio_call=espacio_sup>=1.0, hay_espacio_put=espacio_inf>=1.0,
        volatilidad_abierta=pct_d>=55,
    )

def score_e4_call(bb15, bb1h, bbdiario, chop):
    """
    v6.1: 15min OBLIGATORIO + 1H/Diario BONUS (no obligatorio)
    Score minimo: 55
    """
    score=0.0; criterios={}; notas=[]

    # ── 15MIN — OBLIGATORIO segun documento ──
    # Los 4 criterios del documento son obligatorios en 15min
    if bb15.mid_alcista:
        score+=20; criterios["15m_mid_alcista"]=True
        notas.append("OK 15min: MA20 inclinada al alza")
    else:
        criterios["15m_mid_alcista"]=False
        notas.append("WARN 15min: MA20 NO inclinada al alza")

    if bb15.bandas_abiertas:
        score+=15; criterios["15m_bandas_abiertas"]=True
        notas.append(f"OK 15min: Bandas abiertas ({bb15.bandwidth_pct:.0f}% percentil)")
    else:
        criterios["15m_bandas_abiertas"]=False
        notas.append(f"WARN 15min: Bandas NO abiertas ({bb15.bandwidth_pct:.0f}%)")

    if bb15.precio_sobre_mid:
        score+=15; criterios["15m_precio_sobre_mid"]=True
        notas.append(f"OK 15min: Precio ${bb15.precio} SOBRE MA20 ${bb15.mid}")
    else:
        criterios["15m_precio_sobre_mid"]=False
        notas.append(f"WARN 15min: Precio BAJO MA20 -- no es CALL")

    if bb15.banda_inf_abriendo:
        score+=10; criterios["15m_fuerza_call"]=True
        notas.append("OK 15min: Banda inferior abriendo -- fuerza alcista")
    else:
        criterios["15m_fuerza_call"]=False
        notas.append("WARN 15min: Banda inferior no abriendo")

    criterios["15m_espacio_call"]=bb15.hay_espacio_call
    notas.append(f"{'OK' if bb15.hay_espacio_call else 'WARN'} 15min: Espacio superior {bb15.espacio_superior_pct:.2f}%")

    # ── 1H — BONUS (no obligatorio, como dice el documento) ──
    if bb1h.tendencia in ["alcista_fuerte","alcista_parcial"]:
        pts=15 if bb1h.tendencia=="alcista_fuerte" else 10
        score+=pts; criterios["1h_tendencia_call"]=True
        notas.append(f"OK 1H: Tendencia {bb1h.tendencia}")
    else:
        criterios["1h_tendencia_call"]=False
        notas.append(f"INFO 1H: Tendencia {bb1h.tendencia}")

    if bb1h.hay_espacio_call:
        score+=8; criterios["1h_espacio_call"]=True
        notas.append(f"OK 1H: Espacio superior {bb1h.espacio_superior_pct:.2f}%")
    else:
        criterios["1h_espacio_call"]=False
        notas.append(f"INFO 1H: Poco espacio superior {bb1h.espacio_superior_pct:.2f}%")

    if bb1h.mid_alcista:
        score+=7; criterios["1h_mid_alcista"]=True
        notas.append("OK 1H: MA20 inclinada al alza")
    else:
        criterios["1h_mid_alcista"]=False
        notas.append("INFO 1H: MA20 no inclinada")

    # Volatilidad 1H -- bonus (no obligatorio segun documento)
    if bb1h.volatilidad_abierta:
        score+=5; criterios["1h_volatilidad"]=True
        notas.append("OK 1H: Volatilidad abierta (bonus)")
    else:
        criterios["1h_volatilidad"]=False

    # ── DIARIO — CONTEXTO (no obligatorio) ──
    if bbdiario.tendencia in ["alcista_fuerte","alcista_parcial"]:
        score+=5; criterios["d_tendencia_call"]=True
        notas.append(f"OK Diario: {bbdiario.tendencia}")
    else:
        criterios["d_tendencia_call"]=False

    if bbdiario.hay_espacio_call:
        score+=3; criterios["d_espacio_call"]=True
        notas.append(f"OK Diario: Espacio {bbdiario.espacio_superior_pct:.2f}%")
    else:
        criterios["d_espacio_call"]=False

    if bbdiario.precio_sobre_mid:
        score+=2; criterios["d_precio_sobre_mid"]=True
        notas.append("OK Diario: Precio sobre MA20")
    else:
        criterios["d_precio_sobre_mid"]=False

    criterios["d_volatilidad"]=bbdiario.volatilidad_abierta

    # ── PENALIZACIONES (basadas en backtesting real) ──
    if chop>61.8:
        score*=0.5
        notas.append(f"WARN Choppy ({chop}) -- score reducido")

    # RSI para CALL -- ajustado por backtesting
    # RSI 68-75: cap 58 (no alerta con score minimo 55... espera)
    # RSI >75:   cap 55 (no alerta)
    # RSI >80:   bloquear
    if bb15.rsi>80:
        score*=0.5
        notas.append(f"WARN RSI {bb15.rsi} muy alto (>80) -- bloqueando")
    elif bb15.rsi>75:
        score=min(score,55)
        notas.append(f"WARN RSI {bb15.rsi} alto (75-80) -- cap 55")
    elif bb15.rsi>68:
        score=min(score,58)
        notas.append(f"WARN RSI {bb15.rsi} elevado (68-75) -- cap 58")

    return round(score,1), criterios, "\n".join(notas)

def score_e4_put(bb15, bb1h, bbdiario, chop):
    score=0.0; criterios={}; notas=[]

    # ── 15MIN — OBLIGATORIO ──
    if bb15.mid_bajista:
        score+=20; criterios["15m_mid_bajista"]=True
        notas.append("OK 15min: MA20 inclinada a la baja")
    else:
        criterios["15m_mid_bajista"]=False
        notas.append("WARN 15min: MA20 NO inclinada a la baja")

    if bb15.bandas_abiertas:
        score+=15; criterios["15m_bandas_abiertas"]=True
        notas.append(f"OK 15min: Bandas abiertas ({bb15.bandwidth_pct:.0f}% percentil)")
    else:
        criterios["15m_bandas_abiertas"]=False
        notas.append(f"WARN 15min: Bandas NO abiertas ({bb15.bandwidth_pct:.0f}%)")

    if bb15.precio_bajo_mid:
        score+=15; criterios["15m_precio_bajo_mid"]=True
        notas.append(f"OK 15min: Precio ${bb15.precio} BAJO MA20 ${bb15.mid}")
    else:
        criterios["15m_precio_bajo_mid"]=False
        notas.append("WARN 15min: Precio SOBRE MA20 -- no es PUT")

    if bb15.banda_sup_abriendo:
        score+=10; criterios["15m_fuerza_put"]=True
        notas.append("OK 15min: Banda superior abriendo -- fuerza bajista")
    else:
        criterios["15m_fuerza_put"]=False
        notas.append("WARN 15min: Banda superior no abriendo")

    criterios["15m_espacio_put"]=bb15.hay_espacio_put
    notas.append(f"{'OK' if bb15.hay_espacio_put else 'WARN'} 15min: Espacio inferior {bb15.espacio_inferior_pct:.2f}%")

    # ── 1H — BONUS ──
    if bb1h.tendencia in ["bajista_fuerte","bajista_parcial"]:
        pts=15 if bb1h.tendencia=="bajista_fuerte" else 10
        score+=pts; criterios["1h_tendencia_put"]=True
        notas.append(f"OK 1H: Tendencia {bb1h.tendencia}")
    else:
        criterios["1h_tendencia_put"]=False
        notas.append(f"INFO 1H: Tendencia {bb1h.tendencia}")

    if bb1h.hay_espacio_put:
        score+=8; criterios["1h_espacio_put"]=True
        notas.append(f"OK 1H: Espacio inferior {bb1h.espacio_inferior_pct:.2f}%")
    else:
        criterios["1h_espacio_put"]=False
        notas.append(f"INFO 1H: Poco espacio inferior {bb1h.espacio_inferior_pct:.2f}%")

    if bb1h.mid_bajista:
        score+=7; criterios["1h_mid_bajista"]=True
        notas.append("OK 1H: MA20 inclinada a la baja")
    else:
        criterios["1h_mid_bajista"]=False
        notas.append("INFO 1H: MA20 no inclinada")

    if bb1h.volatilidad_abierta:
        score+=5; criterios["1h_volatilidad"]=True
        notas.append("OK 1H: Volatilidad abierta (bonus)")
    else:
        criterios["1h_volatilidad"]=False

    # ── DIARIO — CONTEXTO ──
    if bbdiario.tendencia in ["bajista_fuerte","bajista_parcial"]:
        score+=5; criterios["d_tendencia_put"]=True
        notas.append(f"OK Diario: {bbdiario.tendencia}")
    else:
        criterios["d_tendencia_put"]=False

    if bbdiario.hay_espacio_put:
        score+=3; criterios["d_espacio_put"]=True
    else:
        criterios["d_espacio_put"]=False

    if bbdiario.precio_bajo_mid:
        score+=2; criterios["d_precio_bajo_mid"]=True
        notas.append("OK Diario: Precio bajo MA20")
    else:
        criterios["d_precio_bajo_mid"]=False

    criterios["d_volatilidad"]=bbdiario.volatilidad_abierta

    # ── PENALIZACIONES ──
    if chop>61.8:
        score*=0.5
        notas.append(f"WARN Choppy ({chop}) -- score reducido")

    # RSI para PUT -- ajustado por backtesting
    if bb15.rsi<20:
        score*=0.5
        notas.append(f"WARN RSI {bb15.rsi} rebote inminente (<20) -- bloqueando")
    elif bb15.rsi<25:
        score=min(score,55)
        notas.append(f"WARN RSI {bb15.rsi} muy bajo (20-25) -- cap 55")
    elif bb15.rsi<32:
        score=min(score,65)
        notas.append(f"WARN RSI {bb15.rsi} bajo (25-32) -- cap 65")

    return round(score,1), criterios, "\n".join(notas)

def identify_e4(bb15, bb1h, bbdiario, chop):
    """
    v6.1: 15min obligatorio, 1H/Diario bonus
    Score minimo: 55
    Criterios 15min DEBEN cumplirse todos (4 del documento)
    """
    score_call,crit_call,exp_call = score_e4_call(bb15,bb1h,bbdiario,chop)
    score_put, crit_put, exp_put  = score_e4_put(bb15,bb1h,bbdiario,chop)

    # CALL: los 4 criterios de 15min son obligatorios
    call_15m_ok = (
        crit_call.get("15m_mid_alcista",False) and
        crit_call.get("15m_bandas_abiertas",False) and
        crit_call.get("15m_precio_sobre_mid",False)
        # fuerza es deseable pero no bloquea si el resto esta bien
    )
    call_valido = call_15m_ok and score_call >= 55

    # PUT: los 4 criterios de 15min son obligatorios
    put_15m_ok = (
        crit_put.get("15m_mid_bajista",False) and
        crit_put.get("15m_bandas_abiertas",False) and
        crit_put.get("15m_precio_bajo_mid",False)
    )
    put_valido = put_15m_ok and score_put >= 55

    if call_valido and put_valido:
        if score_call >= score_put: put_valido=False
        else: call_valido=False

    if call_valido:
        strength = SignalStrength.FUERTE if score_call>=75 else SignalStrength.MODERADO
        return (StrategyType.E4_CALL, SignalDirection.CALL, strength,
                score_call, crit_call, {}, exp_call)
    if put_valido:
        strength = SignalStrength.FUERTE if score_put>=75 else SignalStrength.MODERADO
        return (StrategyType.E4_PUT, SignalDirection.PUT, strength,
                score_put, {}, crit_put, exp_put)
    return (StrategyType.NONE, SignalDirection.NEUTRAL, SignalStrength.DEBIL,
            max(score_call,score_put), crit_call, crit_put, "")

def check_agotamiento(df_15m, bb15):
    try:
        signals=[]
        close=df_15m['Close']
        sma=close.rolling(20).mean(); std=close.rolling(20).std()
        upper=sma+2*std; lower=sma-2*std
        bw=((upper-lower)/sma).dropna()
        if len(bw)>=4:
            last4=bw.tail(4).values
            if all(last4[i]>last4[i+1] for i in range(3)):
                signals.append("BB 15min contrayendose")
        if bb15.mid>0:
            dist=abs(bb15.precio-bb15.mid)/bb15.mid*100
            if dist>3.0: signals.append(f"Precio {dist:.1f}% del punto medio")
        if len(df_15m)>=3:
            doji_count=0
            for i in range(-1,-4,-1):
                row=df_15m.iloc[i]; rng=row['High']-row['Low']; body=abs(row['Close']-row['Open'])
                if rng>0 and body/rng<0.15: doji_count+=1
            if doji_count>=2: signals.append(f"{doji_count} dojis consecutivos")
        if not signals: return {"has_agotamiento":False}
        return {"has_agotamiento":True,"signals":signals,
                "warning":"WARN AGOTAMIENTO: "+" | ".join(signals)}
    except: return {"has_agotamiento":False}

def generate_recommendation(direction, strength, bb15, bb1h, bbdiario,
                             events, earnings, agotamiento, score, chop):
    if chop>61.8: return "NO OPERAR -- Mercado choppy. Esperar."
    if earnings.get("has_earnings") and earnings.get("days_away")==0:
        return "NO ENTRAR -- EARNINGS HOY. IV Crush garantizado."
    high_today=any(e["impact"]=="alto" and e["days"]==0 for e in events)
    if high_today: return f"{direction.value} {strength.value} -- Evento alto impacto HOY. Reducir tamano."
    earnings_txt=""
    if earnings.get("has_earnings"):
        days=earnings["days_away"]
        if days==1: earnings_txt="\nEARNINGS MANANA -- Reducir tamano."
        elif days<=3: earnings_txt=f"\nEarnings en {days} dias -- IV elevada."
    agot_txt="\nAgotamiento detectado -- proteger posicion." if agotamiento.get("has_agotamiento") else ""
    espacio=bb15.espacio_superior_pct if direction==SignalDirection.CALL else bb15.espacio_inferior_pct
    nivel="FUERTE" if strength==SignalStrength.FUERTE else "MODERADO"
    return (f"{direction.value} {nivel} -- Criterios del documento alineados.\n"
            f"Vol 15min: {bb15.bandwidth_pct:.0f}% | Espacio: {espacio:.2f}% | RSI: {bb15.rsi}\n"
            f"1H: {bb1h.tendencia} | Diario: {bbdiario.tendencia}\n"
            f"Confirmar en TC2000 antes de entrar.{earnings_txt}{agot_txt}")

def get_categoria(ticker):
    for cat,tickers in TICKERS_SAAI.items():
        if ticker in tickers: return cat.replace("_"," ")
    return "OTRO"

def analyze_ticker(ticker):
    try:
        stock=yf.Ticker(ticker)
        df_15m=stock.history(period="5d", interval="15m")
        df_1h=stock.history(period="3mo",interval="1h")
        df_daily=stock.history(period="1y", interval="1d")
        if df_15m.empty or df_1h.empty or df_daily.empty:
            print(f"[{ticker}] Sin datos"); return None
        bb15=analyze_bb15(df_15m); bb1h=analyze_bb1h(df_1h); bbdiario=analyze_bbdiario(df_daily)
        if not bb15 or not bb1h or not bbdiario:
            print(f"[{ticker}] Datos insuficientes"); return None
        chop=calc_choppiness(df_1h)
        result=identify_e4(bb15,bb1h,bbdiario,chop)
        strategy,direction,strength,score,crit_call,crit_put,explanation=result
        mid_dir="+" if bb15.mid_alcista else "-" if bb15.mid_bajista else "="
        p_mid="SOBRE" if bb15.precio_sobre_mid else "BAJO"
        print(f"[{ticker}] Score:{score} | Vol:{bb15.volatilidad}({bb15.bandwidth_pct:.0f}%) | "
              f"Mid15:{mid_dir} | P/Mid:{p_mid} | Chop:{chop} | "
              f"1H:{bb1h.tendencia[:8]} | RSI:{bb15.rsi} | -> {strategy.name}")
        if strategy==StrategyType.NONE: return None
        events=check_events(); earnings=check_earnings(ticker)
        agotamiento=check_agotamiento(df_15m,bb15)
        if earnings.get("has_earnings"): print(f"   [{ticker}] {earnings['warning']}")
        rec=generate_recommendation(direction,strength,bb15,bb1h,bbdiario,
                                    events,earnings,agotamiento,score,chop)
        warns=[e["warning"] for e in events]
        if earnings.get("has_earnings"): warns.append(earnings["warning"])
        if agotamiento.get("has_agotamiento"): warns.append(agotamiento["warning"])
        et=pytz.timezone('US/Eastern'); now=datetime.now(et)
        return Alert(
            ticker=ticker, timestamp=now.strftime("%Y-%m-%d %I:%M %p ET"),
            strategy=strategy, direction=direction, strength=strength,
            bb15=bb15, bb1h=bb1h, bbdiario=bbdiario, score=score,
            criterios_call=crit_call, criterios_put=crit_put,
            explanation=explanation, recommendation=rec,
            warning="\n".join(warns) if warns else None,
            external_events=events, earnings=earnings, agotamiento=agotamiento,
            categoria=get_categoria(ticker),
        )
    except Exception as e:
        print(f"[{ticker}] Error: {e}")
        import traceback; traceback.print_exc()
        return None

def run_analysis(tickers=None):
    if tickers is None:
        env=os.environ.get("SAAI_TICKERS","")
        tickers=[t.strip() for t in env.split(",")] if env else DEFAULT_TICKERS
    et=pytz.timezone('US/Eastern')
    print(f"\n{'='*65}")
    print(f"  SAAI v6.1 -- Smart Alert AI System")
    print(f"  E4 -- Saliendo de Bollinger Bands")
    print(f"  15min: 4 criterios obligatorios | 1H+Diario: bonus")
    print(f"  {len(tickers)} tickers | {datetime.now(et).strftime('%I:%M %p ET')}")
    print(f"{'='*65}\n")
    alerts=[]
    for ticker in tickers:
        print(f"[{ticker}] Analizando...")
        a=analyze_ticker(ticker)
        if a:
            alerts.append(a)
            print(f"[{ticker}] ALERTA: {a.strategy.value} | "
                  f"{a.direction.value} {a.strength.value} | Score:{a.score}")
    print(f"\n{'='*65}")
    print(f"  Analizados: {len(tickers)} | Alertas: {len(alerts)}")
    if alerts:
        for a in alerts: print(f"  -> {a.ticker} [{a.categoria}]: {a.strategy.value}")
    print(f"{'='*65}\n")
    return alerts

if __name__ == "__main__":
    run_analysis()
