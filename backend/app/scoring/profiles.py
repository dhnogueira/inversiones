import numpy as np
from datetime import datetime

PROJECTED_ARG_INFLATION = 0.22  # 22% de Inflación Anual Proyectada de Argentina
PROJECTED_DEVAL = 0.42          # 42% de Devaluación del Peso proyectada para activos dolarizados

# Horizontes temporales disponibles
HORIZON_SHORT  = "short"   # hasta 6 meses
HORIZON_MEDIUM = "medium"  # 6 meses – 1 año
HORIZON_LONG   = "long"    # más de 1 año

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
    Estima el retorno esperado para el activo expresado en Pesos Argentinos (ARS),
    empleando TNA para renta fija, retornos históricos ajustados para renta variable/cripto,
    e incorporando la devaluación proyectada del tipo de cambio para activos en USD.
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
        ann_return = tna
        if horizon == HORIZON_SHORT:
            ann_return = tna * 0.5
        elif horizon == HORIZON_LONG:
            ann_return = (1.0 + tna) ** 2 - 1.0
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


# ---------------------------------------------------------------------------
# SCORING ENGINE — DIFERENCIADO POR HORIZONTE TEMPORAL Y PERFIL
# ---------------------------------------------------------------------------
# Principios clave (extraídos de la SKILL de Análisis Cuantitativo):
#   • Corto plazo (≤6M): priorizar liquidez, momentum, letras LECAPs, evitar
#     activos de alta volatilidad o largos plazos. RSI 40–62 ideal.
#     La duration de bonos debe ser < 6 meses.
#   • Mediano plazo (6–12M): balance RSI 50–65, Sharpe relevante, CEDEARs y
#     S&P 500 dolarizados son buenos candidatos junto con bonos de duration ≈ 1 año.
#   • Largo plazo (>1 año): Sharpe dominante, activos de Growth (tecnológicas,
#     commodities, crypto top-cap), Merval local posible. Letras sin sentido.
#     Duration bonos > 1 año.
#
# La clave para diferenciar listas es que:
#   a) El puntaje base de cada categoría varía fuertemente por horizonte.
#   b) Las penalizaciones por volatilidad son asimétricas según el plazo.
#   c) Los activos con ret_1m/ret_6m alto (momentum) son premiados en corto.
#   d) Los activos con ret_12m/sharpe alto son premiados en largo.
#   e) El bonus de superar la inflación del horizonte es el discriminador final.
# ---------------------------------------------------------------------------

def score_asset_for_profile(asset, profile, horizon=HORIZON_MEDIUM):
    """
    Calcula un puntaje de idoneidad (0–100) para un activo según el perfil de riesgo
    y el horizonte temporal seleccionado. Las fórmulas están calibradas para producir
    distribuciones diferenciadas (no saturadas) entre horizontes.
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
    for attr, default in [("volatility", 0.30), ("sharpe", 0.0), ("rsi", 50.0),
                           ("ret_6m", 0.0), ("ret_12m", 0.0), ("ret_1m", 0.0)]:
        val = locals().get(attr)
        if isinstance(val, float) and (np.isnan(val) or np.isinf(val)):
            locals()[attr] = default
    if np.isnan(volatility): volatility = 0.30
    if np.isnan(sharpe): sharpe = 0.0
    if np.isnan(rsi): rsi = 50.0
    if np.isnan(ret_6m): ret_6m = 0.0
    if np.isnan(ret_12m): ret_12m = 0.0
    if np.isnan(ret_1m): ret_1m = 0.0

    # ---- REGLAS DURAS DE ELEGIBILIDAD POR HORIZONTE ----
    # Estas reglas descartan activos que no tienen sentido financiero en ese horizonte.

    if horizon == HORIZON_SHORT:
        # Cripto: solo en perfil agresivo (demasiado volátil para cualquier otro)
        if category == "crypto" and profile != "agresivo":
            return 0.0
        # Bonos: solo si vencen dentro de 6 meses
        if category == "bonos" and maturity:
            try:
                days_to_mat = (datetime.strptime(maturity, "%Y-%m-%d") - datetime.now()).days
                if days_to_mat > 210:
                    return 0.0  # Bono de largo vencimiento: no apto para corto plazo
            except Exception:
                pass
        # Merval en conservador: no apto en corto plazo por volatilidad
        if category == "merval" and profile == "conservador":
            return 0.0

    elif horizon == HORIZON_LONG:
        # Letras: vencen en semanas/meses, sin sentido retener >1 año
        if category == "letras":
            return 0.0  # Letras descartadas para largo plazo
        # Cripto en conservador: nunca
        if category == "crypto" and profile == "conservador":
            return 0.0
        # Activos con momentum de 1M muy positivo pero 12M negativo son señal de trampa
        if ret_1m > 0.10 and ret_12m < -0.10:
            return max(0.0, 20.0)  # trampa de momentum

    elif horizon == HORIZON_MEDIUM:
        # Cripto en conservador: no
        if category == "crypto" and profile == "conservador":
            return 0.0

    # ---- MÉTRICAS DE SCORING DIFERENCIADAS ----

    # 1. RSI — el rango óptimo varía por horizonte
    if horizon == HORIZON_SHORT:
        # RSI entre 40–62: buena zona de entrada de corto plazo
        rsi_center, rsi_width = 51.0, 11.0
        rsi_score = max(0.0, 100.0 - (abs(rsi - rsi_center) / rsi_width) * 60.0)
    elif horizon == HORIZON_LONG:
        # RSI entre 40–70: zona amplia para largo plazo (tendencia importa más)
        rsi_center, rsi_width = 55.0, 15.0
        rsi_score = max(0.0, 100.0 - (abs(rsi - rsi_center) / rsi_width) * 40.0)
    else:
        # RSI entre 50–65: momentum alcista moderado, ideal mediano plazo
        rsi_center, rsi_width = 57.5, 7.5
        rsi_score = max(0.0, 100.0 - (abs(rsi - rsi_center) / rsi_width) * 70.0)
    rsi_score = min(100.0, rsi_score)

    # 2. Sharpe — más relevante a largo plazo; menos a corto
    sharpe_clamped = max(-2.0, min(3.0, sharpe))
    sharpe_score = max(0.0, min(100.0, (sharpe_clamped + 1.0) * 33.3))

    # 3. Retorno — métricas distintas por horizonte
    if horizon == HORIZON_SHORT:
        # Momentum de 1M es el predictor más relevante
        key_ret = (ret_1m * 0.6 + ret_6m * 0.4)
        ret_score = max(0.0, min(100.0, key_ret * 300.0 + 30.0))
    elif horizon == HORIZON_LONG:
        # 12M es el predictor principal; 6M secundario
        key_ret = (ret_12m * 0.75 + ret_6m * 0.25)
        ret_score = max(0.0, min(100.0, key_ret * 110.0 + 25.0))
    else:
        # Balance 6M + 12M
        key_ret = (ret_6m * 0.45 + ret_12m * 0.55)
        ret_score = max(0.0, min(100.0, key_ret * 160.0 + 25.0))

    # 4. Volatilidad — penalización diferenciada por horizonte y perfil
    if horizon == HORIZON_SHORT:
        # En corto plazo la volatilidad es muy dañina
        vol_penalty_scale = 120.0
        vol_threshold = 0.18 if profile == "conservador" else 0.25 if profile == "moderado" else 0.35
    elif horizon == HORIZON_LONG:
        # En largo plazo la volatilidad es más tolerable
        vol_penalty_scale = 60.0
        vol_threshold = 0.30 if profile == "conservador" else 0.40 if profile == "moderado" else 0.60
    else:
        vol_penalty_scale = 90.0
        vol_threshold = 0.22 if profile == "conservador" else 0.30 if profile == "moderado" else 0.45
    vol_penalty = max(0.0, (volatility - vol_threshold) * vol_penalty_scale)

    # ---- SCORE BASE POR CATEGORÍA Y HORIZONTE ----
    # Las categorías base varían sustancialmente entre horizontes para generar listas distintas.
    score = _base_category_score(category, profile, horizon, tna, volatility,
                                  sharpe_score, rsi_score, ret_score, vol_penalty, asset)

    # ---- AJUSTE FINAL: Superación de inflación del horizonte ----
    expected_ret_ars = estimate_expected_return_ars(asset, profile, horizon)
    horizon_inflation = get_horizon_inflation(horizon)

    if expected_ret_ars < horizon_inflation:
        # No supera la inflación: penalización severa que garantiza que NO aparezca en top
        score = min(25.0, score * 0.25)
    elif expected_ret_ars > (horizon_inflation + 0.10):
        # Supera la inflación con spread > 10%: bonificación extra
        inflation_spread_bonus = min(15.0, (expected_ret_ars - horizon_inflation) * 30.0)
        score = min(100.0, score + inflation_spread_bonus)
    elif expected_ret_ars > horizon_inflation:
        # Supera inflación pero apenas: bonificación moderada
        score = min(100.0, score + 5.0)

    return max(0.0, min(100.0, score))


def _base_category_score(category, profile, horizon, tna, volatility,
                          sharpe_score, rsi_score, ret_score, vol_penalty, asset):
    """
    Calcula el puntaje base diferenciado por categoría de activo, perfil y horizonte temporal.
    Aquí reside la lógica financiera central que diferencia qué activos son buenos
    para cada combinación de plazo y tolerancia al riesgo.
    """
    if profile == "conservador":
        return _conservative_base(category, horizon, tna, volatility,
                                   sharpe_score, rsi_score, ret_score, vol_penalty, asset)
    elif profile == "moderado":
        return _moderate_base(category, horizon, tna, volatility,
                               sharpe_score, rsi_score, ret_score, vol_penalty)
    elif profile == "agresivo":
        return _aggressive_base(category, horizon, tna, volatility,
                                 sharpe_score, rsi_score, ret_score, vol_penalty)
    return 0.0


def _conservative_base(category, horizon, tna, volatility,
                        sharpe_score, rsi_score, ret_score, vol_penalty, asset):
    """Conservador: prioridad absoluta en capital garantizado > retorno."""
    maturity_str = asset.get("maturity", "2030-07-01")
    try:
        days_to_mat = (datetime.strptime(maturity_str, "%Y-%m-%d") - datetime.now()).days
        duration = days_to_mat / 365.25
    except Exception:
        duration = 2.0

    if category == "letras":  # Solo válido para short/medium (elegibilidad ya filtrada)
        # Clasificación de calidad: TNA alta = mejor; horizonte corto = muy bueno
        tna_bonus = min(20.0, max(0.0, (tna - 0.30) * 80.0))  # bonus si TNA > 30%
        if horizon == HORIZON_SHORT:
            return max(0.0, 72.0 + tna_bonus - vol_penalty)
        elif horizon == HORIZON_MEDIUM:
            return max(0.0, 62.0 + tna_bonus + sharpe_score * 0.1 - vol_penalty)
        # HORIZON_LONG → descartadas por regla dura

    elif category == "bonos":
        # Bonos: buenos para conservador si no son demasiado largos y tienen TNA razonable
        tna_bonus = min(15.0, max(0.0, (tna - 0.20) * 50.0))
        if horizon == HORIZON_MEDIUM:
            # Duration 6-12 meses: ideal
            dur_bonus = 10.0 if 0.5 <= duration <= 1.2 else max(0.0, 5.0 - abs(duration - 0.9) * 8.0)
            return max(0.0, 58.0 + tna_bonus + dur_bonus - vol_penalty)
        elif horizon == HORIZON_LONG:
            # Bonos de duration > 1 año: aceptables en largo plazo conservador
            dur_bonus = 8.0 if duration > 1.0 else 0.0
            return max(0.0, 52.0 + tna_bonus + dur_bonus + sharpe_score * 0.15 - vol_penalty)

    elif category == "cedears":
        # CEDEARs dolarizadas: cobertura cambiaria, volatilidad moderada exigida
        if volatility > 0.35:
            return max(0.0, 25.0 - vol_penalty)  # demasiado volátil para conservador
        if horizon == HORIZON_SHORT:
            return max(0.0, 38.0 + sharpe_score * 0.20 + rsi_score * 0.10 - vol_penalty)
        elif horizon == HORIZON_MEDIUM:
            return max(0.0, 48.0 + sharpe_score * 0.25 + ret_score * 0.10 - vol_penalty)
        elif horizon == HORIZON_LONG:
            return max(0.0, 56.0 + sharpe_score * 0.30 + ret_score * 0.12 - vol_penalty)

    elif category == "sp500":
        if volatility > 0.30:
            return max(0.0, 20.0 - vol_penalty)
        if horizon == HORIZON_SHORT:
            return max(0.0, 32.0 + sharpe_score * 0.18 + rsi_score * 0.12 - vol_penalty)
        elif horizon == HORIZON_MEDIUM:
            return max(0.0, 45.0 + sharpe_score * 0.22 + ret_score * 0.08 - vol_penalty)
        elif horizon == HORIZON_LONG:
            return max(0.0, 58.0 + sharpe_score * 0.28 + ret_score * 0.10 - vol_penalty)

    elif category == "merval":
        # Para conservador: muy penalizado siempre
        return max(0.0, 10.0 - vol_penalty)

    elif category == "crypto":
        return 0.0  # Nunca en conservador (regla global)

    return 0.0


def _moderate_base(category, horizon, tna, volatility,
                   sharpe_score, rsi_score, ret_score, vol_penalty):
    """
    Moderado: balance entre protección y crecimiento. Las categorías tienen scores
    base sustancialmente diferentes según el horizonte.
    """
    if category == "letras":
        if horizon == HORIZON_SHORT:
            # Letras son IDEALES en corto plazo moderado
            tna_bonus = min(18.0, max(0.0, (tna - 0.25) * 60.0))
            return max(0.0, 68.0 + tna_bonus - vol_penalty * 0.5)
        elif horizon == HORIZON_MEDIUM:
            tna_bonus = min(10.0, max(0.0, (tna - 0.25) * 40.0))
            return max(0.0, 50.0 + tna_bonus - vol_penalty * 0.5)
        # HORIZON_LONG → descartadas por regla dura

    elif category == "bonos":
        if horizon == HORIZON_SHORT:
            return max(0.0, 42.0 + sharpe_score * 0.10 - vol_penalty)
        elif horizon == HORIZON_MEDIUM:
            return max(0.0, 55.0 + sharpe_score * 0.15 + ret_score * 0.08 - vol_penalty)
        elif horizon == HORIZON_LONG:
            return max(0.0, 50.0 + sharpe_score * 0.20 + ret_score * 0.12 - vol_penalty)

    elif category == "cedears":
        if horizon == HORIZON_SHORT:
            # Momentum de CEDEARs es importante en corto
            return max(0.0, 48.0 + rsi_score * 0.25 + ret_score * 0.30 - vol_penalty)
        elif horizon == HORIZON_MEDIUM:
            return max(0.0, 60.0 + sharpe_score * 0.20 + rsi_score * 0.15 + ret_score * 0.12 - vol_penalty)
        elif horizon == HORIZON_LONG:
            # CEDEARs son excelentes para largo plazo moderado por cobertura cambiaria
            return max(0.0, 68.0 + sharpe_score * 0.28 + ret_score * 0.18 - vol_penalty * 0.7)

    elif category == "sp500":
        if horizon == HORIZON_SHORT:
            return max(0.0, 45.0 + rsi_score * 0.22 + ret_score * 0.25 - vol_penalty)
        elif horizon == HORIZON_MEDIUM:
            return max(0.0, 62.0 + sharpe_score * 0.22 + ret_score * 0.15 - vol_penalty)
        elif horizon == HORIZON_LONG:
            return max(0.0, 72.0 + sharpe_score * 0.30 + ret_score * 0.18 - vol_penalty * 0.7)

    elif category == "merval":
        if horizon == HORIZON_SHORT:
            return max(0.0, 30.0 + rsi_score * 0.20 + ret_score * 0.20 - vol_penalty * 1.5)
        elif horizon == HORIZON_MEDIUM:
            return max(0.0, 42.0 + sharpe_score * 0.15 + rsi_score * 0.15 + ret_score * 0.15 - vol_penalty)
        elif horizon == HORIZON_LONG:
            return max(0.0, 50.0 + sharpe_score * 0.20 + ret_score * 0.22 - vol_penalty * 0.8)

    elif category == "crypto":
        if horizon == HORIZON_SHORT:
            return max(0.0, 28.0 + rsi_score * 0.18 + ret_score * 0.22 - vol_penalty * 2.0)
        elif horizon == HORIZON_MEDIUM:
            return max(0.0, 38.0 + sharpe_score * 0.15 + ret_score * 0.20 - vol_penalty * 1.5)
        elif horizon == HORIZON_LONG:
            return max(0.0, 42.0 + sharpe_score * 0.22 + ret_score * 0.25 - vol_penalty * 1.2)

    return 0.0


def _aggressive_base(category, horizon, tna, volatility,
                     sharpe_score, rsi_score, ret_score, vol_penalty):
    """
    Agresivo: maximizar retorno, aceptar alta volatilidad. Crypto y Merval son
    activos de alto interés, especialmente en corto y mediano plazo.
    Largo plazo: S&P 500 growth y crypto de largo aliento lideran.
    """
    if category == "letras":
        if horizon == HORIZON_SHORT:
            tna_bonus = min(10.0, max(0.0, (tna - 0.25) * 30.0))
            return max(0.0, 40.0 + tna_bonus - vol_penalty * 0.3)
        elif horizon == HORIZON_MEDIUM:
            return max(0.0, 28.0 - vol_penalty * 0.5)
        # HORIZON_LONG → descartadas por regla dura

    elif category == "bonos":
        if horizon == HORIZON_SHORT:
            return max(0.0, 35.0 + ret_score * 0.10 - vol_penalty * 0.5)
        elif horizon == HORIZON_MEDIUM:
            return max(0.0, 42.0 + sharpe_score * 0.12 + ret_score * 0.10 - vol_penalty * 0.5)
        elif horizon == HORIZON_LONG:
            return max(0.0, 45.0 + sharpe_score * 0.15 + ret_score * 0.12 - vol_penalty * 0.5)

    elif category == "cedears":
        if horizon == HORIZON_SHORT:
            return max(0.0, 55.0 + rsi_score * 0.22 + ret_score * 0.35 - vol_penalty * 0.8)
        elif horizon == HORIZON_MEDIUM:
            return max(0.0, 65.0 + sharpe_score * 0.18 + ret_score * 0.28 - vol_penalty * 0.7)
        elif horizon == HORIZON_LONG:
            return max(0.0, 72.0 + sharpe_score * 0.25 + ret_score * 0.30 - vol_penalty * 0.5)

    elif category == "sp500":
        if horizon == HORIZON_SHORT:
            return max(0.0, 52.0 + rsi_score * 0.20 + ret_score * 0.30 - vol_penalty * 0.8)
        elif horizon == HORIZON_MEDIUM:
            return max(0.0, 62.0 + sharpe_score * 0.20 + ret_score * 0.28 - vol_penalty * 0.6)
        elif horizon == HORIZON_LONG:
            return max(0.0, 75.0 + sharpe_score * 0.28 + ret_score * 0.35 - vol_penalty * 0.5)

    elif category == "merval":
        if horizon == HORIZON_SHORT:
            # En corto: momentum del Merval es muy valioso para agresivo
            return max(0.0, 60.0 + rsi_score * 0.28 + ret_score * 0.40 - vol_penalty * 0.6)
        elif horizon == HORIZON_MEDIUM:
            return max(0.0, 62.0 + sharpe_score * 0.15 + rsi_score * 0.20 + ret_score * 0.28 - vol_penalty * 0.5)
        elif horizon == HORIZON_LONG:
            return max(0.0, 55.0 + sharpe_score * 0.25 + ret_score * 0.32 - vol_penalty * 0.4)

    elif category == "crypto":
        if horizon == HORIZON_SHORT:
            # Crypto agresivo corto: momentum puro, vol penalizado con factor moderado
            return max(0.0, 62.0 + rsi_score * 0.30 + ret_score * 0.42 - vol_penalty * 0.5)
        elif horizon == HORIZON_MEDIUM:
            return max(0.0, 58.0 + sharpe_score * 0.18 + ret_score * 0.35 - vol_penalty * 0.6)
        elif horizon == HORIZON_LONG:
            # Largo plazo: Sharpe más relevante para evaluar si el activo justifica el riesgo
            return max(0.0, 55.0 + sharpe_score * 0.28 + ret_score * 0.30 - vol_penalty * 0.7)

    return 0.0


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

    # Top 10 General consolidado — excluir activos con score 0
    valid = [a for a in scored_assets if a["score"] > 0]
    top_10 = valid[:10]

    # Agrupación por categorías (Top 5 para cada categoría)
    grouped = {}
    categories_keys = ["merval", "cedears", "sp500", "letras", "bonos", "crypto"]
    for cat in categories_keys:
        cat_assets = [a for a in scored_assets if a["category"] == cat and a["score"] > 0]
        grouped[cat] = cat_assets[:5]

    return {
        "profile": profile,
        "horizon": horizon,
        "top_10": top_10,
        "categories": grouped
    }
