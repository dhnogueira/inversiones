"""
Motor de Scoring Multi-Factor por Horizonte Temporal Calibrado.

Implementa un modelo cuantitativo multi-factor con estilo sectorial
(Defensivo vs Crecimiento) y afinidades asimétricas que permiten carteras
con traslape casi nulo entre horizontes temporales.

Skills utilizadas:
  - Análisis Cuantitativo de Inversiones: RSI, Sharpe, EMA cross, momentum.
  - Optimización de Cartera: asignaciones sectoriales de activos.
"""
import numpy as np
from datetime import datetime

PROJECTED_ARG_INFLATION = 0.22  # 22% de Inflación Anual Proyectada
PROJECTED_DEVAL = 0.42          # 42% de Devaluación Proyectada del Peso

HORIZON_SHORT  = "short"   # hasta 6 meses
HORIZON_MEDIUM = "medium"  # 6 meses – 1 año
HORIZON_LONG   = "long"    # más de 1 año

_HORIZON_INFLATION = {
    HORIZON_SHORT:  0.11,
    HORIZON_MEDIUM: 0.22,
    HORIZON_LONG:   0.47,
}

def get_horizon_inflation(horizon=HORIZON_MEDIUM):
    return _HORIZON_INFLATION.get(horizon, PROJECTED_ARG_INFLATION)


def estimate_expected_return_ars(asset, profile="moderado", horizon=HORIZON_MEDIUM):
    """
    Estima el retorno esperado para el activo expresado en Pesos Argentinos (ARS),
    incorporando TNA para renta fija, retornos históricos ajustados e
    incorporando la devaluación proyectada del tipo de cambio para activos en USD.
    """
    category = asset.get("category")
    currency = asset.get("currency", "ARS")
    tna = asset.get("tna", 0.0)
    ret_12m = asset.get("ret_12m", 0.0)
    ret_6m = asset.get("ret_6m", 0.0)

    # Factor de confianza según perfil
    _PROFILE_RETURN_FACTOR = {"conservador": 0.80, "moderado": 1.00, "agresivo": 1.20}
    factor = _PROFILE_RETURN_FACTOR.get(profile, 1.0)

    if category in ("letras", "bonos"):
        # Calcular T (plazo al vencimiento en años)
        maturity = asset.get("maturity")
        maturity_years = 1.0  # default si no tiene fecha
        if maturity:
            try:
                days = (datetime.strptime(maturity, "%Y-%m-%d") - datetime.now()).days
                maturity_years = max(0.01, days / 365.25)
            except:
                pass

        # Estimar Duración Modificada D*
        if category == "letras":
            modified_duration = maturity_years / (1.0 + tna) if tna > -1.0 else maturity_years
        else:
            modified_duration = max(0.5, min(6.0, maturity_years * 0.6))

        # Estimar cambio de tasa/spread anual (dy) según perfil
        # dy: Conservador (+1.5%), Moderado (-2.0%), Agresivo (-5.0%)
        dy_map = {
            "conservador": 0.015,
            "moderado": -0.020,
            "agresivo": -0.050
        }
        dy = dy_map.get(profile, -0.020)

        # Ganancia/pérdida de capital anual aproximada: -D* * dy
        capital_gain_annual = -modified_duration * dy

        # Retorno anual consolidado: TNA + ganancia de capital anual
        tna_total_annual = tna + capital_gain_annual

        # Escalar conforme al horizonte
        if horizon == HORIZON_SHORT:
            ann_return = tna_total_annual * 0.5
        elif horizon == HORIZON_LONG:
            ann_return = (1.0 + tna_total_annual) ** 2 - 1.0
        else:
            ann_return = tna_total_annual
    else:
        if horizon == HORIZON_SHORT:
            base_ret = ret_6m if ret_6m != 0.0 else ret_12m * 0.5
        elif horizon == HORIZON_LONG:
            base_ret = ret_12m if ret_12m != 0.0 else ret_6m * 2.0
            base_ret = (1.0 + base_ret) ** 2 - 1.0
        else:
            base_ret = ret_12m if ret_12m != 0.0 else ret_6m * 2.0

        base_clamped = max(-0.60, min(2.50, base_ret))
        ann_return = base_clamped * factor

    if currency == "USD":
        if horizon == HORIZON_LONG:
            deval = (1.0 + PROJECTED_DEVAL) ** 2 - 1.0
        elif horizon == HORIZON_SHORT:
            deval = PROJECTED_DEVAL * 0.5
        else:
            deval = PROJECTED_DEVAL

        if category in ("letras", "bonos"):
            ann_return_ars = ((1.0 + ann_return) * (1.0 + deval) - 1.0) * factor
        else:
            ann_return_ars = (1.0 + ann_return) * (1.0 + deval) - 1.0
    else:
        ann_return_ars = ann_return

    return ann_return_ars


# ---- Clasificación de Estilos de Renta Variable ----
# Megacaps de crecimiento secular
GROWTH_TICKERS = ["AAPL", "NVDA", "AMZN", "GOOGL", "META", "LLY", "AVGO", "GOOGL.BA", "AAPL.BA", "NVDA.BA", "AMZN.BA"]
# Acciones defensivas productoras de dividendos y cobertura
DEFENSIVE_TICKERS = ["PG", "KO.BA", "COST", "JPM", "XOM", "MRK", "VALE.BA", "ABBV", "HD", "XOM.BA"]


def _category_affinity(ticker, category, profile, horizon, tna=0.0):
    """
    Asigna una afinidad base (0-100) según la categoría y el estilo del ticker,
    delimitando con precisión la idoneidad por horizonte y perfil.
    """
    if horizon == HORIZON_SHORT:
        if profile == "conservador":
            if category == "letras": return 95
            if category == "bonos": return 70
            if ticker in DEFENSIVE_TICKERS: return 30
            return 0
        elif profile == "moderado":
            if category == "letras": return 85
            if category == "bonos": return 65
            if ticker in DEFENSIVE_TICKERS: return 45
            if ticker in GROWTH_TICKERS: return 10
            return 5
        else:  # agresivo
            if category == "crypto": return 90
            if category == "merval": return 85
            if ticker in GROWTH_TICKERS: return 55
            if category == "letras": return 20
            return 10

    elif horizon == HORIZON_MEDIUM:
        if profile == "conservador":
            if category == "bonos": return 90
            if category == "letras": return 50
            if ticker in DEFENSIVE_TICKERS: return 60
            return 0
        elif profile == "moderado":
            if ticker in GROWTH_TICKERS: return 80
            if ticker in DEFENSIVE_TICKERS: return 75
            if category == "bonos": return 60
            if category == "merval": return 35
            return 10
        else:  # agresivo
            if category == "crypto": return 80
            if category == "merval": return 80
            if ticker in GROWTH_TICKERS: return 80
            if category == "bonos": return 40
            return 15

    else:  # HORIZON_LONG
        if profile == "conservador":
            if ticker in DEFENSIVE_TICKERS: return 95
            if ticker in GROWTH_TICKERS: return 60
            if category == "bonos": return 55
            return 0
        elif profile == "moderado":
            if ticker in GROWTH_TICKERS: return 90
            if ticker in DEFENSIVE_TICKERS: return 80
            if category == "bonos": return 50
            if category == "crypto": return 30
            return 5
        else:  # agresivo
            if ticker in GROWTH_TICKERS: return 95
            if category == "crypto": return 90
            if category == "merval": return 75
            return 5


def _safe(val, default=0.0):
    if val is None:
        return default
    try:
        v = float(val)
        if np.isnan(v) or np.isinf(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


def _normalize(value, low, high):
    if high == low:
        return 50.0
    normed = (value - low) / (high - low) * 100.0
    return max(0.0, min(100.0, normed))


def score_asset_for_profile(asset, profile, horizon=HORIZON_MEDIUM):
    """
    Scoring cuantitativo multi-horizonte. Clasifica y aplica reglas tácticas
    exclusoras para renta fija y timings técnicos rigurosos para renta variable.
    """
    ticker = asset.get("ticker")
    category = asset.get("category")
    trend = asset.get("trend", "Alcista")
    maturity = asset.get("maturity", None)

    ret_1m = _safe(asset.get("ret_1m"))
    ret_3m = _safe(asset.get("ret_3m"))
    ret_6m = _safe(asset.get("ret_6m"))
    ret_12m = _safe(asset.get("ret_12m"))
    volatility = _safe(asset.get("volatility"), 0.30)
    sharpe = _safe(asset.get("sharpe"))
    rsi = _safe(asset.get("rsi"), 50.0)
    tna = _safe(asset.get("tna"))

    momentum_accel = _safe(asset.get("momentum_accel"))
    ema_cross = _safe(asset.get("ema_cross_signal"))
    dist_support = _safe(asset.get("dist_to_support_pct"))
    dist_resist = _safe(asset.get("dist_to_resistance_pct"))
    vol_ratio = _safe(asset.get("vol_short_vs_long"), 1.0)

    # ========================================================================
    # BARRERAS DURAS DE EXCLUSIÓN
    # ========================================================================
    if horizon == HORIZON_SHORT:
        if category == "crypto" and profile != "agresivo":
            return 0.0
        if category == "merval" and profile == "conservador":
            return 0.0
        # No comprar activos equities en tendencia fuertemente bajista
        if trend == "Fuerte Bajista" and category not in ("letras", "bonos"):
            return 0.0
        # Bonos cortos únicamente (<7 meses)
        if category == "bonos" and maturity:
            try:
                days = (datetime.strptime(maturity, "%Y-%m-%d") - datetime.now()).days
                if days > 210:
                    return 0.0
            except:
                pass

    elif horizon == HORIZON_MEDIUM:
        if category == "crypto" and profile == "conservador":
            return 0.0
        if category == "letras" and maturity:
            try:
                days = (datetime.strptime(maturity, "%Y-%m-%d") - datetime.now()).days
                if days < 90:
                    return 0.0
            except:
                pass

    elif horizon == HORIZON_LONG:
        if category == "letras":
            return 0.0
        if category == "crypto" and profile == "conservador":
            return 0.0
        if ret_12m < -0.20 and category not in ("bonos",):
            return 0.0

    # ========================================================================
    # RUTA ESPECIAL DE SCORING PARA RENTA FIJA (Letras y Bonos)
    # ========================================================================
    if category in ("letras", "bonos"):
        base_score = _category_affinity(ticker, category, profile, horizon, tna)
        if tna > 0.0:
            # Recompensar la tasa
            base_score += min(20.0, tna * 35.0)

        expected_ret_ars = estimate_expected_return_ars(asset, profile, horizon)
        h_inf = get_horizon_inflation(horizon)

        if expected_ret_ars < h_inf:
            base_score = min(15.0, base_score * 0.15)
        elif expected_ret_ars > (h_inf + 0.05):
            base_score = min(100.0, base_score + 10.0)

        return max(0.0, min(100.0, round(base_score, 1)))

    # ========================================================================
    # RUTA DE SCORING PARA RENTA VARIABLE / CRIPTOMONEDAS
    # ========================================================================

    # Sub-scores
    f_momentum_short = _normalize(momentum_accel, -0.15, 0.15) * 0.5 + _normalize(ret_1m, -0.10, 0.15) * 0.5
    f_ema_cross = _normalize(ema_cross, -0.15, 0.15)
    f_near_support = _normalize(1.0 - dist_support, 0.5, 1.05)
    f_upside = _normalize(dist_resist, -0.05, 0.20)
    f_vol_stability = _normalize(1.5 - vol_ratio, 0.0, 1.5)

    if horizon == HORIZON_SHORT:
        rsi_dist = abs(rsi - 51.0)
        f_rsi = max(0.0, 100.0 - rsi_dist * 4.5)
    elif horizon == HORIZON_MEDIUM:
        rsi_dist = abs(rsi - 57.5)
        f_rsi = max(0.0, 100.0 - rsi_dist * 5.5)
    else:
        rsi_dist = abs(rsi - 55.0)
        f_rsi = max(0.0, 100.0 - rsi_dist * 3.0)

    f_sharpe = _normalize(sharpe, -1.0, 3.0)

    if horizon == HORIZON_SHORT:
        key_ret = ret_1m * 0.6 + ret_6m * 0.4
    elif horizon == HORIZON_MEDIUM:
        key_ret = ret_6m * 0.45 + ret_12m * 0.55
    else:
        key_ret = ret_12m * 0.75 + ret_6m * 0.25
    f_return = _normalize(key_ret, -0.20, 0.50)

    vol_cap = {"conservador": 0.22, "moderado": 0.35, "agresivo": 0.55}
    v_cap = vol_cap.get(profile, 0.35)
    f_vol_penalty = _normalize(v_cap - volatility, -0.30, v_cap)

    f_category = _category_affinity(ticker, category, profile, horizon, tna)

    trend_scores = {"Fuerte Alcista": 100.0, "Alcista": 70.0, "Bajista": 25.0, "Fuerte Bajista": 0.0}
    f_trend = trend_scores.get(trend, 50.0)

    # Pesos
    if horizon == HORIZON_SHORT:
        weights = {
            "momentum_short": 0.25,
            "near_support":   0.15,
            "upside":         0.10,
            "vol_stability":  0.15,
            "rsi":            0.10,
            "trend":          0.10,
            "return":         0.05,
            "category":       0.05,
            "vol_penalty":    0.05,
            "ema_cross":      0.0,
            "sharpe":         0.0,
        }
    elif horizon == HORIZON_MEDIUM:
        weights = {
            "ema_cross":      0.25,
            "sharpe":         0.20,
            "return":         0.15,
            "rsi":            0.10,
            "trend":          0.10,
            "category":       0.08,
            "vol_penalty":    0.05,
            "upside":         0.05,
            "vol_stability":  0.02,
            "momentum_short": 0.0,
            "near_support":   0.0,
        }
    else:
        weights = {
            "sharpe":         0.35,
            "return":         0.25,
            "ema_cross":      0.15,
            "trend":          0.10,
            "category":       0.10,
            "vol_penalty":    0.05,
            "rsi":            0.0,
            "upside":         0.0,
            "vol_stability":  0.0,
            "momentum_short": 0.0,
            "near_support":   0.0,
        }

    score = sum(weights[k] * factor_values[k] for k, factor_values in [
        ("momentum_short", {"momentum_short": f_momentum_short}),
        ("ema_cross", {"ema_cross": f_ema_cross}),
        ("near_support", {"near_support": f_near_support}),
        ("upside", {"upside": f_upside}),
        ("vol_stability", {"vol_stability": f_vol_stability}),
        ("rsi", {"rsi": f_rsi}),
        ("sharpe", {"sharpe": f_sharpe}),
        ("return", {"return": f_return}),
        ("vol_penalty", {"vol_penalty": f_vol_penalty}),
        ("category", {"category": f_category}),
        ("trend", {"trend": f_trend}),
    ])

    # Penalizaciones adicionales tácticas de Corto Plazo
    if horizon == HORIZON_SHORT:
        if momentum_accel < -0.02:
            score -= 30.0
        if rsi > 62.0:
            score -= 25.0
        if dist_resist < 0.02:
            score -= 20.0
        if ret_1m < 0.0:
            score -= 35.0

    # Penalizaciones adicionales para Largo Plazo
    if horizon == HORIZON_LONG:
        if profile != "agresivo" and volatility > 0.38:
            score -= 20.0
        if ret_12m < 0.0:
            score -= 25.0

    # Ajuste por inflación
    expected_ret_ars = estimate_expected_return_ars(asset, profile, horizon)
    h_inf = get_horizon_inflation(horizon)

    if expected_ret_ars < h_inf:
        score = min(15.0, score * 0.15)
    elif expected_ret_ars > (h_inf + 0.10):
        spread_bonus = min(12.0, (expected_ret_ars - h_inf) * 20.0)
        score = min(100.0, score + spread_bonus)

    # Umbral de calidad mínimo por perfil para evitar activos de débil encaje
    # Conservador exige el umbral más alto (busca certeza), Agresivo acepta más riesgo
    profile_thresholds = {"conservador": 45.0, "moderado": 42.0, "agresivo": 38.0}
    min_score = profile_thresholds.get(profile, 42.0)
    if category not in ("letras", "bonos") and score < min_score:
        return 0.0

    return max(0.0, min(100.0, round(score, 1)))


def get_recommendations_by_profile(market_data, profile, horizon=HORIZON_MEDIUM):
    """
    Filtra, califica y ordena los activos de mercado para obtener el Top 10
    del perfil y del horizonte temporal solicitado.
    """
    scored_assets = []
    for asset in market_data:
        score = score_asset_for_profile(asset, profile, horizon)
        scored_assets.append({**asset, "score": round(score, 1)})

    scored_assets.sort(key=lambda x: x["score"], reverse=True)
    valid = [a for a in scored_assets if a["score"] > 0]

    top_10 = valid[:10]

    grouped = {}
    CATEGORY_MIN = 5
    CATEGORY_MAX = 10
    for cat in ["merval", "cedears", "sp500", "letras", "bonos", "crypto"]:
        # Activos que pasaron los filtros de calidad (score > 0)
        cat_valid = [a for a in scored_assets if a["category"] == cat and a["score"] > 0]
        # Si no alcanza el mínimo, rellenar con los "menos malos" (score = 0 pero ordenados por retorno)
        if len(cat_valid) < CATEGORY_MIN:
            cat_fallback = [
                a for a in scored_assets
                if a["category"] == cat and a["score"] == 0.0
            ]
            # Ordenar fallback por retorno ARS estimado (mejor primero)
            cat_fallback.sort(
                key=lambda a: estimate_expected_return_ars(a, profile, horizon),
                reverse=True
            )
            needed = CATEGORY_MIN - len(cat_valid)
            # Marcar con flag para que la UI pueda mostrar una advertencia visual
            for fb in cat_fallback[:needed]:
                fb = {**fb, "fallback": True}
                cat_valid.append(fb)
        grouped[cat] = cat_valid[:CATEGORY_MAX]

    return {
        "profile": profile,
        "horizon": horizon,
        "top_10": top_10,
        "categories": grouped,
    }
