"""
asset_funnel.py — Motor de Selección en Cascada (Funnel de 3 Etapas)

Arquitectura:
    Universo total (~550-600 activos)
       ↓ Etapa 1: Filtro de Liquidez  (dollar volume 20d — barato, EOD)
    Universo líquido (~150-250)
       ↓ Etapa 2: Filtro Técnico Grueso  (EMA50/200, RSI, ATR — vectorizado)
    Candidatos (~30-50)
       ↓ Etapa 3: Scoring Multiparámetro compuesto ponderado (5 dimensiones)
    Shortlist por perfil + horizonte (~5-15)
       ↓ Ranking final
    Oportunidades finales (top 5-10 por categoría)

Clave de diseño:
    - Cada etapa reduce drásticamente el universo ANTES del análisis más costoso.
    - Los pesos y umbrales son sensibles al PERFIL (conservador/moderado/agresivo)
      y al HORIZONTE (short/medium/long), siguiendo la misma lógica de profiles.py.
    - Cada activo que pasa el funnel lleva consigo TODAS las métricas necesarias
      para alimentar el modal de detalle (compatible con /api/asset-analysis).
    - Caché en disco de 24h (por perfil+horizonte) para no impactar rate-limits.
"""

import os
import json
import time
import numpy as np
import pandas as pd
import yfinance as yf
import asyncio


from app.config import CACHE_DIR

# ============================================================
# UNIVERSO EXTENDIDO DE SCREENING (~550-600 activos)
# ============================================================

# S&P 500 — lista ampliada de los ~250 mayores por capitalización
SP500_UNIVERSE = [
    # Mega-caps (Top 50)
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "BRK-B",
    "LLY", "AVGO", "JPM", "TSLA", "XOM", "UNH", "PG", "V", "MA", "HD",
    "COST", "MRK", "ABBV", "JNJ", "WMT", "NFLX", "BAC", "CRM", "AMD",
    "ORCL", "CVX", "KO", "PEP", "TMO", "ABT", "MCD", "PM", "CSCO",
    "ACN", "IBM", "TXN", "LIN", "DHR", "NEE", "MS", "GS", "BLK",
    "SPGI", "CAT", "HON", "RTX", "LOW",
    # Large-caps (50-150)
    "UPS", "INTU", "QCOM", "AMAT", "ISRG", "T", "VZ", "AXP", "AMGN",
    "SYK", "GILD", "CVS", "MO", "USB", "WFC", "DIS", "SBUX", "NOW",
    "ADBE", "SNOW", "CRWD", "UBER", "ABNB", "DKNG", "SQ", "PLTR",
    "ARM", "MRVL", "KLAC", "LRCX", "PANW", "ZS", "MU", "INTC",
    "F", "GM", "NKE", "TGT", "DE", "BA", "GE", "MMM", "EMR", "ETN",
    "FDX", "VALE", "RIO", "BHP", "MELI", "SE", "NU", "GLOB",
    # Mid-caps con liquidez
    "APP", "DECK", "DUOL", "CELH", "HOOD", "COIN", "RBLX", "U",
    "AFRM", "UPST", "SOFI", "OPEN", "RIVN", "LCID", "NIO",
    "BABA", "JD", "BIDU", "TCOM", "PDD",
    "TSM", "ASML", "SAP", "NVO", "SHEL", "TTE", "BP",
    "WPM", "AEM", "NEM", "GOLD", "GFI",
    "SMCI", "ENPH", "FSLR", "PLUG", "BE",
    "ZM", "DOCU", "TWLO", "MDB", "DDOG", "NET", "FSLY",
    "SHOP", "ETSY", "WISH", "W", "PINS",
    "ROKU", "TTD", "MGNI", "PUBM",
    "SFM", "CHEF", "ELF", "ULTA",
    "AXON", "S", "SAIC", "LDOS",
    "VRTX", "REGN", "MRNA", "BNTX", "NVAX",
    "HCA", "THC", "CNC", "MOH", "ELV",
    "MCO", "MSCI", "ICE", "CME", "CBOE",
    "PLD", "AMT", "EQIX", "DLR", "PSA",
    "XLU", "XLE", "XLF", "XLK", "XLV",  # ETFs sectoriales como benchmark
]

# CEDEARs — panel ampliado
CEDEARS_UNIVERSE = [
    "AAPL.BA", "MSFT.BA", "TSLA.BA", "MELI.BA", "KO.BA", "NVDA.BA",
    "AMZN.BA", "META.BA", "GOOGL.BA", "XOM.BA", "BABA.BA", "VALE.BA",
    "PBR.BA", "GGLD.BA", "DESP.BA",
    "NFLX.BA", "AMD.BA", "INTC.BA", "BRKB.BA", "WMT.BA",
    "MA.BA", "JPM.BA", "BA.BA", "DISN.BA",
    "GS.BA", "MSFT.BA", "ORCL.BA", "CSCO.BA", "IBM.BA",
]

# Merval completo (~30 tickers activos)
MERVAL_UNIVERSE = [
    "YPFD.BA", "GGAL.BA", "PAMP.BA", "ALUA.BA", "TXAR.BA", "BMA.BA",
    "CEPU.BA", "TGSU2.BA", "EDN.BA", "LOMA.BA", "CRES.BA", "TECO2.BA",
    "SUPV.BA", "VALO.BA", "BYMA.BA",
    "IRSA.BA", "HARG.BA", "MIRG.BA", "CGPA2.BA", "BOLT.BA",
    "COME.BA", "CAPX.BA", "MOLA.BA", "RICH.BA", "AGRO.BA",
    "SEMI.BA", "FERR.BA", "REGE.BA", "METR.BA", "GBAN.BA",
]

# Crypto — los de mayor volumen
CRYPTO_UNIVERSE = [
    "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "XRP-USD",
    "ADA-USD", "DOGE-USD", "AVAX-USD", "LINK-USD", "DOT-USD",
    "MATIC-USD", "LTC-USD", "TRX-USD", "ATOM-USD", "UNI-USD",
    "NEAR-USD", "APT-USD", "INJ-USD", "ARB-USD", "OP-USD",
    "SUI-USD", "SEI-USD", "WIF-USD", "JUP-USD",
]

# Universo completo (sin duplicados)
FULL_UNIVERSE = list(dict.fromkeys(
    SP500_UNIVERSE + CEDEARS_UNIVERSE + MERVAL_UNIVERSE + CRYPTO_UNIVERSE
))

# Mapa de categorías
_CATEGORIES: dict[str, str] = {}
for _t in SP500_UNIVERSE:    _CATEGORIES[_t] = "sp500"
for _t in CEDEARS_UNIVERSE:  _CATEGORIES[_t] = "cedears"
for _t in MERVAL_UNIVERSE:   _CATEGORIES[_t] = "merval"
for _t in CRYPTO_UNIVERSE:   _CATEGORIES[_t] = "crypto"

# ============================================================
# CONFIGURACIÓN DE UMBRALES POR PERFIL Y HORIZONTE
# ============================================================

# --- Etapa 1: Liquidez mínima (dollar volume diario promedio 20d) ---
# Conservador: exige más liquidez (entrada/salida fácil)
# Agresivo: acepta menor liquidez para capturar oportunidades emergentes
_LIQUIDITY_THRESHOLDS = {
    "sp500": {"conservador": 10_000_000, "moderado": 5_000_000,  "agresivo": 2_000_000},
    "cedears": {"conservador": 1_000_000, "moderado": 500_000,   "agresivo": 200_000},
    "merval": {"conservador": 500_000,    "moderado": 200_000,   "agresivo": 100_000},
    "crypto": {"conservador": 50_000_000, "moderado": 20_000_000,"agresivo": 5_000_000},
}

# --- Etapa 2: Parámetros técnicos gruesos por horizonte ---
# Short: exige tendencia EMA50 y RSI centrado
# Medium: EMA50/200 o pendiente positiva; RSI amplio
# Long: solo exige no estar en colapso (tendencia EMA200); RSI muy amplio
_TECH_PARAMS = {
    "short":  {"rsi_min": 35, "rsi_max": 65, "require_ema50": True,  "atr_max_pct": 0.08},
    "medium": {"rsi_min": 30, "rsi_max": 70, "require_ema50": False, "atr_max_pct": 0.12},
    "long":   {"rsi_min": 25, "rsi_max": 75, "require_ema50": False, "atr_max_pct": 0.15},
}

# --- Etapa 3: Pesos del scoring compuesto por horizonte ---
# Short: momentum y cercanía al soporte pesan más
# Medium: EMA cross y Sharpe pesan más (tendencia consolidada)
# Long: Sharpe y retorno histórico pesan más (calidad del activo)
_SCORE_WEIGHTS = {
    "short":  {"tendencia": 0.20, "momentum": 0.30, "vol_relativo": 0.15, "valuacion": 0.20, "riesgo": 0.15},
    "medium": {"tendencia": 0.25, "momentum": 0.20, "vol_relativo": 0.20, "valuacion": 0.25, "riesgo": 0.10},
    "long":   {"tendencia": 0.20, "momentum": 0.15, "vol_relativo": 0.20, "valuacion": 0.35, "riesgo": 0.10},
}

# Top N activos a retornar por categoría
_TOP_N = {"conservador": 5, "moderado": 8, "agresivo": 10}

# Perfil: si el score mínimo para pasar la Etapa 3 varía por perfil
_MIN_COMPOSITE_SCORE = {"conservador": 55.0, "moderado": 45.0, "agresivo": 35.0}

# Penalización adicional de volatilidad por perfil (para la Etapa 3)
_VOL_CAP = {"conservador": 0.20, "moderado": 0.35, "agresivo": 0.60}

# Peso del bonus de velas japonesas (bonus aditivo, fuera del 100% base).
# Fórmula: score_final = clamp(score_5dim + _CANDLE_WEIGHT*(candle_subscore-50), 0, 100)
# Impacto máximo: ±5 puntos con peso=0.10, ±7.5 puntos con peso=0.15.
# Bajar a 0.0 para desactivar sin tocar el resto del código.
_CANDLE_WEIGHT: float = 0.10


# ============================================================
# HELPERS
# ============================================================

def _calc_rsi(close: pd.Series, period: int = 14) -> float:
    """RSI estándar con suavizado Wilder."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.dropna()
    return float(val.iloc[-1]) if not val.empty else 50.0


def _calc_atr(df: pd.DataFrame, period: int = 14) -> float:
    """ATR 14d relativo al precio (porcentual)."""
    if "High" not in df.columns or "Low" not in df.columns:
        return 0.05  # default
    high = df["High"]
    low = df["Low"]
    close_prev = df["Close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - close_prev).abs(),
        (low - close_prev).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=period, min_periods=period).mean().iloc[-1]
    current_price = float(df["Close"].iloc[-1])
    return float(atr / current_price) if current_price > 0 else 0.05


def _normalize(value: float, low: float, high: float) -> float:
    """Normaliza un valor al rango [0, 100]."""
    if high == low:
        return 50.0
    return max(0.0, min(100.0, (value - low) / (high - low) * 100.0))


def _safe(val, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        v = float(val)
        return default if (np.isnan(v) or np.isinf(v)) else v
    except (TypeError, ValueError):
        return default


# ============================================================
# ETAPA 1 — FILTRO DE LIQUIDEZ
# ============================================================

def _stage1_liquidity(
    ticker: str,
    df: pd.DataFrame,
    category: str,
    profile: str
) -> bool:
    """
    Filtra por dollar volume promedio en los últimos 20 días operativos.
    Comparable entre categorías porque usa precio × volumen (USD o ARS).
    """
    if df is None or df.empty or len(df) < 5:
        return False

    close = df["Close"].dropna()
    volume = df["Volume"].dropna() if "Volume" in df.columns else pd.Series(dtype=float)

    if volume.empty:
        # Sin datos de volumen: pasa solo si es crypto (volumen nominal grande)
        return category == "crypto"

    # Alinear por índice para evitar errores de longitud
    aligned = pd.concat([close, volume], axis=1).dropna()
    aligned.columns = ["close", "volume"]

    lookback = min(20, len(aligned))
    if lookback < 3:
        return False

    recent = aligned.iloc[-lookback:]
    dollar_volume = float((recent["close"] * recent["volume"]).mean())

    threshold = _LIQUIDITY_THRESHOLDS.get(category, {}).get(profile, 1_000_000)
    return dollar_volume >= threshold


# ============================================================
# ETAPA 2 — FILTRO TÉCNICO GRUESO
# ============================================================

def _stage2_technical(
    ticker: str,
    df: pd.DataFrame,
    horizon: str
) -> bool:
    """
    Aplica filtros técnicos vectorizados (pandas/numpy puro, sin loops activo por activo).
    Reduce el universo a candidatos 'interesantes' sin decidir nada todavía.
    """
    if df is None or df.empty or len(df) < 60:
        return False

    close = df["Close"].dropna()
    if len(close) < 60:
        return False

    params = _TECH_PARAMS.get(horizon, _TECH_PARAMS["medium"])

    # --- RSI ---
    rsi = _calc_rsi(close)
    if not (params["rsi_min"] <= rsi <= params["rsi_max"]):
        return False

    # --- Tendencia EMA ---
    ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
    current_price = float(close.iloc[-1])

    if params["require_ema50"]:
        # Short: precio debe estar sobre EMA50
        if current_price < ema50:
            return False
    else:
        # Medium/Long: acepta precio bajo EMA50 si EMA50 tiene pendiente positiva
        ema50_30d_ago = float(close.ewm(span=50, adjust=False).mean().iloc[-min(30, len(close))])
        slope_ema50 = (ema50 - ema50_30d_ago) / ema50_30d_ago if ema50_30d_ago > 0 else 0.0
        if current_price < ema50 and slope_ema50 < 0.0:
            return False  # Bajista sin señal de recuperación

    # --- ATR relativo (volatilidad) ---
    atr_pct = _calc_atr(df)
    if atr_pct > params["atr_max_pct"]:
        return False  # Demasiado errático para este horizonte

    # Mínimo de ATR para descartar activos planos sin movimiento real
    if atr_pct < 0.001:
        return False

    return True


# ============================================================
# ETAPA 3 — SCORING MULTIPARÁMETRO COMPUESTO
# ============================================================

def _compute_full_metrics(ticker: str, df: pd.DataFrame, category: str) -> dict | None:
    """
    Calcula todas las métricas del activo (compatible con el formato de
    yfinance_service.compute_asset_metrics para que el modal de detalle funcione igual).
    """
    if df is None or df.empty or len(df) < 60:
        return None

    close = df["Close"].dropna()
    volume = df["Volume"].dropna() if "Volume" in df.columns else pd.Series(dtype=float)

    if len(close) < 60:
        return None

    current_price = float(close.iloc[-1])

    # Retornos
    def _ret(n):
        return float((close.iloc[-1] / close.iloc[-min(n, len(close))] - 1)) if len(close) >= n else 0.0

    ret_1m  = _ret(21)
    ret_3m  = _ret(63)
    ret_6m  = _ret(126)
    ret_12m = _ret(252)

    # Volatilidad anualizada
    daily_returns = close.pct_change().dropna()
    volatility = float(daily_returns.std() * np.sqrt(252)) if len(daily_returns) > 0 else 0.30

    # Sharpe
    rf = 0.04
    ann_return = ret_12m if ret_12m != 0 else ret_6m * 2
    sharpe = float((ann_return - rf) / volatility) if volatility > 0 else 0.0

    # RSI
    rsi = _calc_rsi(close)

    # EMAs
    ema50_series = close.ewm(span=50, adjust=False).mean()
    ema200_series = close.ewm(span=200, adjust=False).mean()
    ema_50 = float(ema50_series.iloc[-1])
    ema_200 = float(ema200_series.iloc[-1])

    ema_200_slope = 0.0
    if len(ema200_series) >= 30:
        prev = float(ema200_series.iloc[-30])
        ema_200_slope = float((ema_200 - prev) / prev) if prev > 0 else 0.0

    # EMA cross signal (normalizado)
    ema_cross_signal = float((ema_50 - ema_200) / ema_200) if ema_200 > 0 else 0.0

    # Momentum aceleración
    momentum_accel = float(ret_1m - ret_3m)

    # Soporte / Resistencia (percentiles)
    lookback = min(90, len(close))
    recent_close = close.iloc[-lookback:]
    support = float(np.percentile(recent_close, 10))
    resistance = float(np.percentile(recent_close, 90))

    dist_to_support_pct = float((current_price - support) / current_price) if current_price > 0 else 0.0
    dist_to_resistance_pct = float((resistance - current_price) / current_price) if current_price > 0 else 0.0

    # Volatilidad corta vs larga
    vol_20d = float(daily_returns.iloc[-20:].std() * np.sqrt(252)) if len(daily_returns) >= 20 else volatility
    vol_short_vs_long = float(vol_20d / volatility) if volatility > 0.001 else 1.0

    # Drawdown desde máximo 52w
    high_52w = float(close.iloc[-min(252, len(close)):].max())
    drawdown_pct = float((high_52w - current_price) / high_52w) if high_52w > 0 else 0.0

    # Dollar volume promedio 20d
    if not volume.empty:
        aligned = pd.concat([close, volume], axis=1).dropna()
        aligned.columns = ["close", "volume"]
        lookback_vol = min(20, len(aligned))
        dollar_vol_20d = float((aligned["close"].iloc[-lookback_vol:] * aligned["volume"].iloc[-lookback_vol:]).mean())
    else:
        dollar_vol_20d = 0.0

    # Tendencia
    trend = "Alcista" if current_price > ema_200 else "Bajista"
    if ema_50 > ema_200 and current_price > ema_50:
        trend = "Fuerte Alcista"
    elif ema_50 < ema_200 and current_price < ema_50:
        trend = "Fuerte Bajista"

    # ATR relativo
    atr_pct = _calc_atr(df)

    return {
        "ticker": ticker,
        "name": ticker.replace(".BA", "").replace("-USD", ""),
        "category": category,
        "price": round(current_price, 4),
        "currency": "USD" if category in ("sp500", "crypto") else "ARS",
        "ret_1m": round(ret_1m, 4),
        "ret_3m": round(ret_3m, 4),
        "ret_6m": round(ret_6m, 4),
        "ret_12m": round(ret_12m, 4),
        "volatility": round(volatility, 4),
        "sharpe": round(sharpe, 2),
        "rsi": round(rsi, 1),
        "ema_50": round(ema_50, 4),
        "ema_200": round(ema_200, 4),
        "ema_200_slope": round(ema_200_slope, 4),
        "ema_cross_signal": round(ema_cross_signal, 4),
        "trend": trend,
        "momentum_accel": round(momentum_accel, 4),
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "dist_to_support_pct": round(dist_to_support_pct, 4),
        "dist_to_resistance_pct": round(dist_to_resistance_pct, 4),
        "vol_short_vs_long": round(vol_short_vs_long, 4),
        "drawdown_pct": round(drawdown_pct, 4),
        "high_52w": round(high_52w, 2),
        "dollar_vol_20d": round(dollar_vol_20d, 0),
        "atr_pct": round(atr_pct, 4),
        "timestamp": time.time(),
    }


def _stage3_composite_score(
    metrics: dict,
    profile: str,
    horizon: str,
    df: "pd.DataFrame | None" = None,
) -> tuple[float, dict]:
    """
    Scoring compuesto ponderado de 5 dimensiones + bonus opcional de velas.

    score_base = w1*score_tendencia + w2*score_momentum + w3*score_vol_relativo
                 + w4*score_valuacion + w5*score_riesgo_beneficio
    score_final = clamp(score_base + _CANDLE_WEIGHT*(candle_subscore-50), 0, 100)

    Returns:
        (score_final, desglose_dict)
    """
    weights = _SCORE_WEIGHTS.get(horizon, _SCORE_WEIGHTS["medium"])
    vol_cap = _VOL_CAP.get(profile, 0.35)

    # ── Dim 1: TENDENCIA ──────────────────────────────────────────────────
    # EMA cross normalizado + dirección de la EMA200 (pendiente)
    ema_cross = _safe(metrics.get("ema_cross_signal"), 0.0)
    ema_slope = _safe(metrics.get("ema_200_slope"), 0.0)
    trend_val = metrics.get("trend", "Bajista")
    trend_map = {"Fuerte Alcista": 100.0, "Alcista": 70.0, "Bajista": 30.0, "Fuerte Bajista": 0.0}
    f_trend_dir = trend_map.get(trend_val, 50.0)
    f_ema_cross = _normalize(ema_cross, -0.15, 0.15)
    f_ema_slope = _normalize(ema_slope, -0.05, 0.05)
    score_tendencia = f_trend_dir * 0.50 + f_ema_cross * 0.30 + f_ema_slope * 0.20

    # ── Dim 2: MOMENTUM ───────────────────────────────────────────────────
    # Retorno relativo según horizonte + aceleración de momentum + RSI ideal
    ret_1m  = _safe(metrics.get("ret_1m"), 0.0)
    ret_3m  = _safe(metrics.get("ret_3m"), 0.0)
    ret_6m  = _safe(metrics.get("ret_6m"), 0.0)
    ret_12m = _safe(metrics.get("ret_12m"), 0.0)
    rsi     = _safe(metrics.get("rsi"), 50.0)
    mom_accel = _safe(metrics.get("momentum_accel"), 0.0)

    if horizon == "short":
        key_ret = ret_1m * 0.6 + ret_3m * 0.4
        rsi_ideal = 52.0; rsi_bw = 4.0
    elif horizon == "long":
        key_ret = ret_12m * 0.7 + ret_6m * 0.3
        rsi_ideal = 55.0; rsi_bw = 3.0
    else:
        key_ret = ret_6m * 0.5 + ret_12m * 0.5
        rsi_ideal = 57.0; rsi_bw = 4.5

    f_return  = _normalize(key_ret, -0.20, 0.50)
    f_rsi     = max(0.0, 100.0 - abs(rsi - rsi_ideal) * rsi_bw)
    f_mom_acc = _normalize(mom_accel, -0.10, 0.10)
    score_momentum = f_return * 0.50 + f_rsi * 0.30 + f_mom_acc * 0.20

    # ── Dim 3: VOLUMEN RELATIVO ───────────────────────────────────────────
    # Dollar volume como proxy de liquidez y aceptación de mercado
    dollar_vol = _safe(metrics.get("dollar_vol_20d"), 0.0)
    category = metrics.get("category", "sp500")
    # Escalas de referencia por categoría (p50=bueno, p90=excelente)
    vol_ref = {
        "sp500":   (5_000_000,   500_000_000),
        "cedears": (500_000,     20_000_000),
        "merval":  (200_000,     10_000_000),
        "crypto":  (10_000_000, 1_000_000_000),
    }
    v_low, v_high = vol_ref.get(category, (1_000_000, 100_000_000))
    score_vol_relativo = _normalize(dollar_vol, v_low, v_high)

    # ── Dim 4: VALUACIÓN / CALIDAD ────────────────────────────────────────
    # Sharpe, drawdown (oportunidad de compra con descuento), volatilidad aceptable
    sharpe = _safe(metrics.get("sharpe"), 0.0)
    drawdown = _safe(metrics.get("drawdown_pct"), 0.0)
    volatility = _safe(metrics.get("volatility"), 0.30)

    f_sharpe = _normalize(sharpe, -1.0, 3.0)
    f_vol_penalty = _normalize(vol_cap - volatility, -0.30, vol_cap)

    # Drawdown: zona de descuento deseable por perfil
    if profile == "conservador":
        # Conservador: prefiere activos near ATH (drawdown bajo)
        f_drawdown = _normalize(1.0 - drawdown, 0.60, 1.0)
    elif profile == "agresivo":
        # Agresivo: prefiere activos con descuento (drawdown moderado = oportunidad)
        ideal_dd = 0.25
        f_drawdown = max(0.0, 100.0 - abs(drawdown - ideal_dd) * 400.0)
    else:
        # Moderado: equilibrio, descuento moderado está bien
        ideal_dd = 0.15
        f_drawdown = max(0.0, 100.0 - abs(drawdown - ideal_dd) * 300.0)

    score_valuacion = f_sharpe * 0.45 + f_vol_penalty * 0.30 + f_drawdown * 0.25

    # ── Dim 5: RIESGO/BENEFICIO ───────────────────────────────────────────
    # Distancia al soporte (cercanía = bajo riesgo de baja)
    # Distancia a resistencia (espacio de upside)
    dist_sup = _safe(metrics.get("dist_to_support_pct"), 0.10)
    dist_res = _safe(metrics.get("dist_to_resistance_pct"), 0.10)

    # Bajo riesgo = precio cerca del soporte
    f_near_support = _normalize(1.0 - dist_sup, 0.50, 1.05)
    # Buen upside = amplio espacio hasta resistencia
    f_upside = _normalize(dist_res, -0.05, 0.25)

    # Ratio R/B
    rb_ratio = dist_res / dist_sup if dist_sup > 0 else 1.0
    f_rb = _normalize(rb_ratio, 0.5, 4.0)

    score_riesgo = f_near_support * 0.35 + f_upside * 0.35 + f_rb * 0.30

    # ── Score final compuesto ─────────────────────────────────────────────
    composite = (
        weights["tendencia"]    * score_tendencia +
        weights["momentum"]     * score_momentum +
        weights["vol_relativo"] * score_vol_relativo +
        weights["valuacion"]    * score_valuacion +
        weights["riesgo"]       * score_riesgo
    )

    # Bonus / penalizaciones de exclusión compatibles con profiles.py
    if horizon == "short":
        if _safe(metrics.get("momentum_accel"), 0.0) < -0.05:
            composite -= 15.0
        if rsi > 68.0:
            composite -= 10.0

    if horizon == "long":
        if volatility > vol_cap and profile != "agresivo":
            composite -= 20.0
        if ret_12m < 0.0:
            composite -= 20.0

    # ── Bonus: PATRÓN DE VELAS (aditivo — no redistribuye pesos base) ──────
    # Fórmula: score_final = clamp(composite_5dim + _CANDLE_WEIGHT*(subscore-50), 0, 100)
    # neutral=50 → +0 pts; bullish_engulfing fuerte → +~4 pts; bearish fuerte → -~4 pts
    candle_detail: dict = {
        "valor": 50.0,
        "patron_detectado": "sin_patron",
        "fuerza_base": 0.0,
        "contexto_mult": 1.0,
        "contexto_descripcion": "no_aplica",
        "descripcion": "Sin patrón de velas relevante detectado",
        "peso_aplicado": f"{int(_CANDLE_WEIGHT * 100)}%",
    }
    if df is not None and _CANDLE_WEIGHT > 0:
        try:
            from app.services.candlestick_scorer import calcular_subscore_velas
            candle_subscore, candle_info = calcular_subscore_velas(df)
            candle_bonus = _CANDLE_WEIGHT * (candle_subscore - 50.0)
            composite += candle_bonus
            candle_detail = {
                **candle_info,
                "valor": round(candle_subscore, 1),
                "bonus_pts": round(candle_bonus, 2),
                "peso_aplicado": f"{int(_CANDLE_WEIGHT * 100)}%",
            }
        except Exception as e:
            print(f"[candlestick] Error calculando subscore de velas: {e}")

    score_final = max(0.0, min(100.0, round(composite, 1)))

    desglose = {
        "tendencia":         round(score_tendencia,     1),
        "momentum":          round(score_momentum,      1),
        "volumen_relativo":  round(score_vol_relativo,  1),
        "valuacion":         round(score_valuacion,     1),
        "riesgo":            round(score_riesgo,        1),
        "patron_velas":      candle_detail,
    }

    return score_final, desglose


async def _run_funnel_fallback(profile: str, horizon: str) -> dict:
    """
    Fallback del funnel: usa los datos de mercado cacheados (yfinance_service)
    en lugar de descargar datos frescos. Se activa cuando yfinance.download falla.

    Retorna el mismo formato que run_funnel:
    { "pipeline": {...}, "results": {cat: [assets...]} }
    """
    import math

    def _safe_float(v, d=0.0):
        if v is None:
            return d
        try:
            f = float(v)
            return d if (math.isnan(f) or math.isinf(f)) else f
        except (TypeError, ValueError):
            return d

    try:
        from app.services.yfinance_service import fetch_yfinance_market_data
        from app.services.arg_fixed_income import fetch_arg_fixed_income_data
        from app.scoring.profiles import get_recommendations_by_profile

        yf_data = await fetch_yfinance_market_data(use_cache_only=True)
        fi_data = await fetch_arg_fixed_income_data(force_refresh=False)
        all_assets = yf_data + fi_data

        if not all_assets:
            print(f"[funnel_fallback:{profile}/{horizon}] Sin datos en caché.")
            return {"pipeline": {"universe_size": 0, "timestamp": time.time(), "profile": profile, "horizon": horizon, "source": "fallback_empty"}, "results": {}}

        results = get_recommendations_by_profile(all_assets, profile, horizon)
        categories = results.get("categories", {})
        top_n = _TOP_N.get(profile, 8)
        min_score = _MIN_COMPOSITE_SCORE.get(profile, 45.0)

        results_by_cat: dict[str, list] = {cat: [] for cat in ["sp500", "cedears", "merval", "crypto"]}
        total = 0
        for cat, assets in categories.items():
            valid = [a for a in assets if a.get("score", 0) >= min_score]
            valid.sort(key=lambda x: x.get("score", 0), reverse=True)
            for a in valid[:top_n]:
                entry = {
                    "ticker": a.get("ticker", ""),
                    "name": a.get("name", a.get("ticker", "")),
                    "category": cat,
                    "price": _safe_float(a.get("price")),
                    "currency": a.get("currency", "ARS"),
                    "funnel_score": _safe_float(a.get("score")),
                    "ret_1m": _safe_float(a.get("ret_1m")),
                    "ret_6m": _safe_float(a.get("ret_6m")),
                    "ret_12m": _safe_float(a.get("ret_12m")),
                    "volatility": _safe_float(a.get("volatility"), 0.25),
                    "sharpe": _safe_float(a.get("sharpe")),
                    "rsi": _safe_float(a.get("rsi"), 50),
                    "trend": a.get("trend", "Alcista"),
                    "ema_50": _safe_float(a.get("ema_50")),
                    "ema_200": _safe_float(a.get("ema_200")),
                    "momentum_accel": _safe_float(a.get("momentum_accel")),
                    "dist_to_support_pct": _safe_float(a.get("dist_to_support_pct"), 0.1),
                    "dist_to_resistance_pct": _safe_float(a.get("dist_to_resistance_pct"), 0.1),
                    "dollar_vol_20d": _safe_float(a.get("dollar_vol_20d")),
                    "drawdown_pct": _safe_float(a.get("drawdown_pct")),
                    "profile": profile,
                    "horizon": horizon,
                    "timestamp": time.time(),
                    "source": "fallback",
                }
                results_by_cat.setdefault(cat, []).append(entry)
                total += 1

        print(f"[funnel_fallback:{profile}/{horizon}] Generado {total} activos desde caché de recomendaciones.")
        return {
            "pipeline": {
                "universe_size": len(all_assets),
                "stage1_passed": total,
                "stage2_passed": total,
                "final_count": total,
                "timestamp": time.time(),
                "profile": profile,
                "horizon": horizon,
                "source": "fallback_recommendations",
            },
            "results": results_by_cat,
        }
    except Exception as e:
        print(f"[funnel_fallback:{profile}/{horizon}] Error en fallback: {e}")
        return {"pipeline": {"universe_size": 0, "timestamp": time.time(), "profile": profile, "horizon": horizon}, "results": {}}


# ============================================================
# FUNCIÓN PRINCIPAL DEL FUNNEL
# ============================================================

async def run_funnel(
    profile: str = "moderado",
    horizon: str = "medium",
    force_refresh: bool = False
) -> dict:
    """
    Ejecuta el funnel completo de 3 etapas y retorna los activos que
    superaron todos los filtros, ordenados por score compuesto descendente.

    Retorna:
        {
          "pipeline": {
              "universe_size": int,
              "stage1_passed": int,
              "stage2_passed": int,
              "final_count": int,
              "timestamp": float,
              "profile": str,
              "horizon": str,
          },
          "results": {
              "sp500": [...],
              "cedears": [...],
              "merval": [...],
              "crypto": [...],
          }
        }
    """
    cache_key = f"funnel_{profile}_{horizon}.json"
    cache_path = os.path.join(CACHE_DIR, cache_key)
    cache_ttl = 86400  # 24 horas

    if not force_refresh and os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            age = time.time() - cached.get("pipeline", {}).get("timestamp", 0)
            if age < cache_ttl:
                print(f"[funnel:{profile}/{horizon}] Usando caché ({int(age/3600)}h). Saltando descarga.")
                return cached
        except Exception as e:
            print(f"[funnel] Error leyendo caché {cache_key}: {e}")

    print(f"[funnel:{profile}/{horizon}] Iniciando escaneo de {len(FULL_UNIVERSE)} tickers...")

    try:
        from app.services.data_providers import fetch_ohlcv_batch
        raw_dict = await fetch_ohlcv_batch(FULL_UNIVERSE, _CATEGORIES, days=365, max_concurrent=10)
    except Exception as e:
        print(f"[funnel] Error descargando datos multi-fuente: {e}. Usando fallback desde recomendaciones.")
        return await _run_funnel_fallback(profile, horizon)


    # ── Verificar que el download retornó datos útiles ──────────────────
    if not raw_dict:
        print(f"[funnel:{profile}/{horizon}] No se obtuvieron datos de ninguna fuente. Usando fallback.")
        return await _run_funnel_fallback(profile, horizon)

    pipeline_meta = {
        "universe_size": len(FULL_UNIVERSE),
        "stage1_passed": 0,
        "stage2_passed": 0,
        "final_count": 0,
        "timestamp": time.time(),
        "profile": profile,
        "horizon": horizon,
    }

    # ── Etapa 1 + 2: iteración rápida (sin cómputo pesado) ───────────────
    stage2_candidates: list[tuple[str, pd.DataFrame, str]] = []

    for ticker in FULL_UNIVERSE:
        category = _CATEGORIES.get(ticker, "sp500")
        try:
            df = raw_dict.get(ticker, pd.DataFrame())
            if df.empty:
                continue

            # ETAPA 1: Liquidez
            if not _stage1_liquidity(ticker, df, category, profile):
                continue
            pipeline_meta["stage1_passed"] += 1

            # ETAPA 2: Técnico grueso
            if not _stage2_technical(ticker, df, horizon):
                continue
            pipeline_meta["stage2_passed"] += 1

            stage2_candidates.append((ticker, df, category))

        except Exception:
            continue

    print(
        f"[funnel:{profile}/{horizon}] "
        f"Etapa 1: {pipeline_meta['stage1_passed']}/{len(FULL_UNIVERSE)} | "
        f"Etapa 2: {pipeline_meta['stage2_passed']}/{pipeline_meta['stage1_passed']}"
    )

    # ── Etapa 3: Scoring profundo sobre candidatos reducidos ─────────────
    min_score = _MIN_COMPOSITE_SCORE.get(profile, 45.0)
    top_n = _TOP_N.get(profile, 8)
    results_by_cat: dict[str, list] = {"sp500": [], "cedears": [], "merval": [], "crypto": []}

    for ticker, df, category in stage2_candidates:
        metrics = _compute_full_metrics(ticker, df, category)
        if metrics is None:
            continue

        composite, desglose = _stage3_composite_score(metrics, profile, horizon, df=df)
        if composite < min_score:
            continue

        metrics["funnel_score"] = composite
        metrics["desglose"] = desglose
        metrics["profile"] = profile
        metrics["horizon"] = horizon
        results_by_cat.setdefault(category, []).append(metrics)

    # Ordenar y truncar por categoría
    for cat in results_by_cat:
        results_by_cat[cat].sort(key=lambda x: x["funnel_score"], reverse=True)
        results_by_cat[cat] = results_by_cat[cat][:top_n]

    pipeline_meta["final_count"] = sum(len(v) for v in results_by_cat.values())
    print(
        f"[funnel:{profile}/{horizon}] "
        f"Etapa 3: {pipeline_meta['final_count']} activos finales "
        f"(umbral mínimo score={min_score})"
    )

    output = {"pipeline": pipeline_meta, "results": results_by_cat}

    # Guardar caché
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[funnel] Error guardando caché: {e}")

    return output


# ============================================================
# VARIANTE: ejecutar el funnel para todos los perfiles/horizontes
# (usado por el scheduler diario)
# ============================================================

async def run_funnel_all_profiles() -> dict:
    """
    Ejecuta el funnel para los 9 combos (3 perfiles × 3 horizontes).
    Retorna un dict {f'{profile}_{horizon}': <resultado>}.
    """
    import asyncio
    profiles = ["conservador", "moderado", "agresivo"]
    horizons = ["short", "medium", "long"]
    all_results = {}
    for p in profiles:
        for h in horizons:
            try:
                result = await run_funnel(profile=p, horizon=h, force_refresh=True)
                all_results[f"{p}_{h}"] = result
            except Exception as e:
                print(f"[funnel_all] Error en {p}/{h}: {e}")
    return all_results
