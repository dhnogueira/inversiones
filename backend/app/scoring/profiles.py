import numpy as np
from datetime import datetime

PROJECTED_ARG_INFLATION = 0.22  # 22% de Inflación Anual Proyectada de Argentina
PROJECTED_DEVAL = 0.42          # 42% de Devaluación del Peso proyectada para activos dolarizados

# Horizontes temporales disponibles
HORIZON_SHORT  = "short"   # hasta 6 meses
HORIZON_MEDIUM = "medium"  # 6 meses – 1 año (comportamiento previo default)
HORIZON_LONG   = "long"    # más de 1 año

# Factores de confianza en la proyección de retorno por perfil.
# Conservador aplica un recorte = proyecta el escenario pesimista.
# Moderado usa el retorno histórico puro.
# Agresivo aplica un ajuste optimista = proyecta el escenario favorable.
_PROFILE_RETURN_FACTOR = {
    "conservador": 0.80,
    "moderado":    1.00,
    "agresivo":    1.25,
}

# Inflación de referencia por horizonte
# Corto: semestral proyectada (≈11%), Mediano: anual (22%), Largo: bianual acumulada (≈47%)
_HORIZON_INFLATION = {
    HORIZON_SHORT:  0.11,
    HORIZON_MEDIUM: 0.22,
    HORIZON_LONG:   0.47,
}

def get_horizon_inflation(horizon=HORIZON_MEDIUM):
    return _HORIZON_INFLATION.get(horizon, PROJECTED_ARG_INFLATION)


def estimate_expected_return_ars(asset, profile="moderado", horizon=HORIZON_MEDIUM):
    """
    Estima el retorno anualizado esperado para el activo expresado en Pesos Argentinos (ARS),
    empleando TNA para renta fija, retornos históricos ajustados para renta variable/cripto,
    e incorporando la devaluación proyectada del tipo de cambio para activos denominados en USD.

    El argumento `profile` ajusta la proyección según el nivel de optimismo razonable para cada perfil.
    El argumento `horizon` escala la proyección al período de tiempo evaluado.
    """
    category = asset.get("category")
    currency = asset.get("currency", "ARS")
    tna = asset.get("tna", 0.0)
    ret_12m = asset.get("ret_12m", 0.0)
    ret_6m = asset.get("ret_6m", 0.0)

    # Factor de confianza según perfil
    factor = _PROFILE_RETURN_FACTOR.get(profile, 1.0)

    if category in ("letras", "bonos"):
        # Renta fija: la TNA es el retorno contractual
        # Corto plazo: proyectar solo 6M del rendimiento anual
        ann_return = tna
        if horizon == HORIZON_SHORT:
            # Retorno efectivo en 6 meses (capitalización simple)
            ann_return = tna * 0.5
        elif horizon == HORIZON_LONG:
            # Proyectar 2 años de capitalización compuesta
            ann_return = (1.0 + tna) ** 2 - 1.0
    else:
        # Renta variable / cripto
        # Horizonte corto: pesa más el retorno reciente (6M)
        # Horizonte largo: pesa más el retorno de 12M
        if horizon == HORIZON_SHORT:
            base_ret = ret_6m if ret_6m != 0.0 else ret_12m * 0.5
        elif horizon == HORIZON_LONG:
            base_ret = ret_12m if ret_12m != 0.0 else ret_6m * 2.0
            # Proyección de largo plazo: compounding 2 años
            base_ret = (1.0 + base_ret) ** 2 - 1.0
        else:
            base_ret = ret_12m if ret_12m != 0.0 else ret_6m * 2.0

        base_clamped = max(-0.60, min(2.50, base_ret))
        ann_return = base_clamped * factor

    if currency == "USD":
        # Activos dolarizados: capturan la devaluación del peso
        # Para largo plazo la devaluación acumulada es mayor (compounding)
        if horizon == HORIZON_LONG:
            deval = (1.0 + PROJECTED_DEVAL) ** 2 - 1.0  # 2 años de devaluación acumulada
        elif horizon == HORIZON_SHORT:
            deval = PROJECTED_DEVAL * 0.5  # 6 meses de devaluación
        else:
            deval = PROJECTED_DEVAL

        if category in ("letras", "bonos"):
            ann_return_ars = ((1.0 + ann_return) * (1.0 + deval) - 1.0) * factor
        else:
            ann_return_ars = (1.0 + ann_return) * (1.0 + deval) - 1.0
    else:
        ann_return_ars = ann_return

    return ann_return_ars


def score_asset_for_profile(asset, profile, horizon=HORIZON_MEDIUM):
    """
    Calcula un puntaje de idoneidad (0 a 100) para un activo según el perfil de riesgo
    y el horizonte temporal seleccionado.
    """
    category = asset.get("category")
    volatility = asset.get("volatility", 0.30)
    sharpe = asset.get("sharpe", 0.0)
    rsi = asset.get("rsi", 50.0)
    ret_6m = asset.get("ret_6m", 0.0)
    ret_12m = asset.get("ret_12m", 0.0)
    ret_1m = asset.get("ret_1m", 0.0)
    tna = asset.get("tna", 0.0)
    maturity = asset.get("maturity", None)

    # Sanitizar NaN / Inf
    for v in [volatility, sharpe, rsi, ret_6m, ret_12m, ret_1m]:
        if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
            v = 0.0
    if np.isnan(volatility) or np.isinf(volatility): volatility = 0.30
    if np.isnan(sharpe) or np.isinf(sharpe): sharpe = 0.0
    if np.isnan(rsi) or np.isinf(rsi): rsi = 50.0
    if np.isnan(ret_6m) or np.isinf(ret_6m): ret_6m = 0.0
    if np.isnan(ret_12m) or np.isinf(ret_12m): ret_12m = 0.0
    if np.isnan(ret_1m) or np.isinf(ret_1m): ret_1m = 0.0

    # ---- RSI óptimo varía por horizonte ----
    # Corto: RSI 40-60 (momentum de entrada, evitar sobrecompra)
    # Mediano: RSI 50-65 (fuerza alcista moderada)
    # Largo: RSI menos relevante, usar 45-70 (tendencia amplia)
    if horizon == HORIZON_SHORT:
        rsi_center, rsi_mult = 50.0, 3.0
    elif horizon == HORIZON_LONG:
        rsi_center, rsi_mult = 55.0, 2.0
    else:
        rsi_center, rsi_mult = 58.5, 2.5

    rsi_purity = 100.0 - abs(rsi - rsi_center) * rsi_mult
    rsi_score = max(0.0, min(100.0, rsi_purity))

    # Sharpe Score — más relevante en mediano y largo plazo
    sharpe_score = max(0.0, min(100.0, (sharpe + 0.5) * 40.0))

    # Retorno score ponderado según horizonte
    if horizon == HORIZON_SHORT:
        # Pesa más momentum reciente (1M y 6M)
        ret_score = max(0.0, min(100.0, (ret_1m * 0.5 + ret_6m * 0.5) * 200.0 + 30.0))
    elif horizon == HORIZON_LONG:
        # Pesa principalmente el retorno de 12M
        ret_score = max(0.0, min(100.0, (ret_12m * 0.7 + ret_6m * 0.3) * 120.0 + 30.0))
    else:
        # Mediano: balance entre 6M y 12M
        ret_score = max(0.0, min(100.0, (ret_6m * 0.4 + ret_12m * 0.6) * 150.0 + 30.0))

    # Bonificación RSI óptimo
    if horizon == HORIZON_SHORT:
        rsi_bonus = 8.0 if (40.0 <= rsi <= 62.0) else 0.0
    elif horizon == HORIZON_LONG:
        rsi_bonus = 5.0 if (45.0 <= rsi <= 70.0) else 0.0
    else:
        rsi_bonus = 8.0 if (50.0 <= rsi <= 65.0) else 0.0

    # ---- Filtrado de activos inválidos por horizonte ----
    # (Retornar 0 para activos que no aplican en cierto horizonte)
    if horizon == HORIZON_SHORT:
        # Corto plazo: letras y bonos cortos son ideales; cripto solo para agresivo
        if category == "crypto" and profile != "agresivo":
            return 0.0
        # Bonos con vencimiento > 6 meses: penalizar en corto (no aplica)
        if category == "bonos" and maturity:
            try:
                days_to_mat = (datetime.strptime(maturity, "%Y-%m-%d") - datetime.now()).days
                if days_to_mat > 210:  # más de 7 meses
                    return max(0.0, 30.0)  # bono demasiado largo para corto plazo
            except Exception:
                pass
    elif horizon == HORIZON_LONG:
        # Largo plazo: letras (TNA fija corta) son poco atractivas; cripto solo agresivo
        if category == "letras":
            return max(0.0, 25.0)  # letras penalizadas en largo plazo
        if category == "crypto" and profile == "conservador":
            return 0.0

    # ---- Score por perfil ----
    if profile == "conservador":
        score = calculate_conservative_score(category, volatility, sharpe_score, rsi_score, ret_score, asset, horizon)
    elif profile == "moderado":
        score = calculate_moderate_score(category, volatility, sharpe_score, rsi_score, ret_score, horizon)
    elif profile == "agresivo":
        score = calculate_aggressive_score(category, volatility, sharpe_score, rsi_score, ret_score, horizon)
    else:
        score = 0.0

    if score > 15.0:
        score = score + rsi_bonus

    # Validar meta de ganarle a la inflación proyectada para el horizonte
    expected_ret_ars = estimate_expected_return_ars(asset, profile, horizon)
    horizon_inflation = get_horizon_inflation(horizon)
    if expected_ret_ars <= horizon_inflation:
        score = min(35.0, score - 30.0)
    else:
        if expected_ret_ars > (horizon_inflation + 0.05):
            score = min(100.0, score + 3.0)

    return max(0.0, min(100.0, score))


def calculate_conservative_score(category, volatility, sharpe_score, rsi_score, ret_score, asset, horizon=HORIZON_MEDIUM):
    tna = asset.get("tna", 0.40)
    maturity_str = asset.get("maturity", "2030-07-09")

    try:
        days_to_mat = (datetime.strptime(maturity_str, "%Y-%m-%d") - datetime.now()).days
        duration = days_to_mat / 365.25
    except Exception:
        duration = 4.0

    if category == "letras":
        if horizon == HORIZON_LONG:
            # Letras no sirven para largo plazo conservador
            return 30.0
        # Corto y mediano: letras son el activo defensivo ideal
        return min(100.0, 90.0 + (tna * 10.0))

    elif category == "bonos":
        if horizon == HORIZON_SHORT:
            # Solo bonos cortos en corto plazo conservador
            return 75.0 + (sharpe_score * 0.15) if duration <= 0.6 else 20.0
        elif horizon == HORIZON_LONG:
            # Bonos aceptables para largo plazo si tienen buen Sharpe
            return 60.0 + (sharpe_score * 0.20) if duration > 1.0 else 45.0
        # Mediano: lógica original
        if duration > 1.2:
            return 45.0 + (sharpe_score * 0.10)
        return 75.0 + (sharpe_score * 0.15)

    elif category == "cedears":
        if horizon == HORIZON_LONG:
            # CEDEARs dolarizados son buenos para largo plazo conservador
            if volatility < 0.28:
                return 65.0 + (sharpe_score * 0.25)
            return 35.0
        if volatility < 0.22:
            return 55.0 + (sharpe_score * 0.2)
        return 20.0

    elif category == "sp500":
        if horizon == HORIZON_LONG:
            # SP500 excelente para largo plazo como activo dolarizado defensivo
            if volatility < 0.25:
                return 70.0 + (sharpe_score * 0.25)
            return 40.0
        if volatility < 0.20:
            return 60.0 + (sharpe_score * 0.20)
        return 30.0

    elif category == "merval":
        return 15.0

    elif category == "crypto":
        return 0.0

    return 0.0


def calculate_moderate_score(category, volatility, sharpe_score, rsi_score, ret_score, horizon=HORIZON_MEDIUM):
    if horizon == HORIZON_SHORT:
        base_category_scores = {
            "letras":  85.0,
            "bonos":   72.0,
            "sp500":   65.0,
            "cedears": 62.0,
            "merval":  45.0,
            "crypto":  40.0
        }
        vol_threshold = 0.20
    elif horizon == HORIZON_LONG:
        base_category_scores = {
            "sp500":   82.0,
            "cedears": 80.0,
            "bonos":   70.0,
            "merval":  55.0,
            "letras":  30.0,   # letras no recomendadas a largo plazo
            "crypto":  50.0
        }
        vol_threshold = 0.30
    else:
        # Mediano: comportamiento original
        base_category_scores = {
            "sp500":   75.0,
            "cedears": 72.0,
            "bonos":   65.0,
            "letras":  60.0,
            "merval":  50.0,
            "crypto":  45.0
        }
        vol_threshold = 0.25

    base = base_category_scores.get(category, 0.0)
    vol_penalty = max(0.0, (volatility - vol_threshold) * 80.0)

    # En largo plazo el Sharpe tiene más peso
    if horizon == HORIZON_LONG:
        score = base + (sharpe_score * 0.30) + (rsi_score * 0.10) + (ret_score * 0.10) - vol_penalty
    elif horizon == HORIZON_SHORT:
        score = base + (sharpe_score * 0.10) + (rsi_score * 0.20) + (ret_score * 0.20) - vol_penalty
    else:
        score = base + (sharpe_score * 0.2) + (rsi_score * 0.15) + (ret_score * 0.1) - vol_penalty

    return max(0.0, min(95.0, score))


def calculate_aggressive_score(category, volatility, sharpe_score, rsi_score, ret_score, horizon=HORIZON_MEDIUM):
    if horizon == HORIZON_SHORT:
        base_category_scores = {
            "crypto":  85.0,
            "merval":  80.0,
            "cedears": 72.0,
            "sp500":   68.0,
            "bonos":   50.0,
            "letras":  35.0
        }
    elif horizon == HORIZON_LONG:
        base_category_scores = {
            "sp500":   85.0,
            "crypto":  83.0,
            "cedears": 80.0,
            "merval":  70.0,
            "bonos":   55.0,
            "letras":  15.0   # letras inútiles en largo plazo agresivo
        }
    else:
        # Mediano: comportamiento original
        base_category_scores = {
            "crypto":  80.0,
            "sp500":   78.0,
            "merval":  75.0,
            "cedears": 75.0,
            "bonos":   60.0,
            "letras":  30.0
        }

    base = base_category_scores.get(category, 0.0)

    # Momentum muy pesado en corto plazo agresivo
    if horizon == HORIZON_SHORT:
        score = base + (ret_score * 0.45) + (rsi_score * 0.25) + (sharpe_score * 0.05)
    elif horizon == HORIZON_LONG:
        score = base + (ret_score * 0.25) + (rsi_score * 0.15) + (sharpe_score * 0.20)
    else:
        score = base + (ret_score * 0.35) + (rsi_score * 0.2) + (sharpe_score * 0.1)

    if volatility < 0.10:
        score -= 20.0

    return max(0.0, min(100.0, score))


def get_recommendations_by_profile(market_data, profile, horizon=HORIZON_MEDIUM):
    """
    Ordena y retorna el top 10 general y agrupado por categorías para un perfil y horizonte dados.
    """
    scored_assets = []
    for asset in market_data:
        score = score_asset_for_profile(asset, profile, horizon)
        scored_assets.append({
            **asset,
            "score": round(score, 1)
        })

    # Ordenar por puntaje descendente
    scored_assets.sort(key=lambda x: x["score"], reverse=True)

    # Top 10 General consolidado
    top_10 = scored_assets[:10]

    # Agrupación por categorías (Top 5 para cada categoría)
    grouped = {}
    categories_keys = ["merval", "cedears", "sp500", "letras", "bonos", "crypto"]
    for cat in categories_keys:
        cat_assets = [a for a in scored_assets if a["category"] == cat]
        grouped[cat] = cat_assets[:5]

    return {
        "profile": profile,
        "horizon": horizon,
        "top_10": top_10,
        "categories": grouped
    }
