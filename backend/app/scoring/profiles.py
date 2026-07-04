import numpy as np

PROJECTED_ARG_INFLATION = 0.22  # 22% de Inflación Anual Proyectada de Argentina
PROJECTED_DEVAL = 0.42          # 42% de Devaluación del Peso proyectada para activos dolarizados

def estimate_expected_return_ars(asset):
    """
    Estima el retorno anualizado esperado para el activo expresado en Pesos Argentinos (ARS),
    empleando TNA para renta fija, retornos históricos ajustados para renta variable/cripto,
    e incorporando la devaluación proyectada del tipo de cambio para activos denominados en USD.
    """
    category = asset.get("category")
    currency = asset.get("currency", "ARS")
    tna = asset.get("tna", 0.0)
    ret_12m = asset.get("ret_12m", 0.0)
    ret_6m = asset.get("ret_6m", 0.0)
    
    # Estimación base anualizada (en su moneda origen)
    base_ret = ret_12m if ret_12m != 0.0 else ret_6m * 2.0
    
    if category in ("letras", "bonos"):
        ann_return = tna
    else:
        # Acotamos retornos para evitar proyecciones especulativas extremas
        ann_return = max(-0.30, min(1.20, base_ret))
        
    if currency == "USD":
        # Activos dolarizados (S&P 500, Crypto, etc): se benefician de la devaluación local
        ann_return_ars = (1.0 + ann_return) * (1.0 + PROJECTED_DEVAL) - 1.0
    else:
        ann_return_ars = ann_return
        
    return ann_return_ars

def score_asset_for_profile(asset, profile):
    """
    Calcula un puntaje de idoneidad (0 a 100) para un activo según el perfil de riesgo seleccionado.
    Optimizado para un horizonte de mediano plazo (6-12 meses).
    Incorpora penalizaciones severas si el activo no supera la inflación anual proyectada en Argentina.
    """
    category = asset.get("category")
    volatility = asset.get("volatility", 0.30)
    sharpe = asset.get("sharpe", 0.0)
    rsi = asset.get("rsi", 50.0)
    ret_6m = asset.get("ret_6m", 0.0)
    ret_12m = asset.get("ret_12m", 0.0)
    
    # Manejar posibles NaNs e infinitos causados por volatilidades ínfimas o errores
    if np.isnan(volatility) or np.isinf(volatility): volatility = 0.30
    if np.isnan(sharpe) or np.isinf(sharpe): sharpe = 0.0
    if np.isnan(rsi) or np.isinf(rsi): rsi = 50.0
    if np.isnan(ret_6m) or np.isinf(ret_6m): ret_6m = 0.0
    if np.isnan(ret_12m) or np.isinf(ret_12m): ret_12m = 0.0

    # Normalizaciones y variables auxiliares
    # RSI óptimo de mediano plazo es alcista moderado (52 a 65). Penalizamos extremos de sobrecompra (>75) o sobreventa profunda (<35).
    rsi_purity = 100.0 - abs(rsi - 58.5) * 2.5
    rsi_score = max(0.0, min(100.0, rsi_purity))
    
    # Normalización de Sharpe (Sharpe óptimo > 1, Sharpe bajo < 0)
    sharpe_score = max(0.0, min(100.0, (sharpe + 0.5) * 40.0))
    
    # Retornos de mediano plazo (combina 6 meses y 12 meses)
    ret_score = max(0.0, min(100.0, (ret_6m * 0.4 + ret_12m * 0.6) * 150.0 + 30.0))

    # Bonificación RSI óptimo (RSI 50-65: tendencia estable con espacio de crecimiento)
    rsi_bonus = 8.0 if (50.0 <= rsi <= 65.0) else 0.0

    if profile == "conservador":
        score = calculate_conservative_score(category, volatility, sharpe_score, rsi_score, ret_score, asset)
    elif profile == "moderado":
        score = calculate_moderate_score(category, volatility, sharpe_score, rsi_score, ret_score)
    elif profile == "agresivo":
        score = calculate_aggressive_score(category, volatility, sharpe_score, rsi_score, ret_score)
    else:
        score = 0.0

    if score > 15.0:
        score = score + rsi_bonus
        
    # Validar meta de ganarle a la inflación proyectada en pesos
    expected_ret_ars = estimate_expected_return_ars(asset)
    if expected_ret_ars <= PROJECTED_ARG_INFLATION:
        # Penalización drástica: no califica como sugerencia recomendada (queda por debajo de 40 puntos)
        score = min(35.0, score - 30.0)
    else:
        # Bonificación ligera si supera con margen (ej: > 25% de retorno anual)
        if expected_ret_ars > (PROJECTED_ARG_INFLATION + 0.05):
            score = min(100.0, score + 3.0)

    return max(0.0, min(100.0, score))

def calculate_conservative_score(category, volatility, sharpe_score, rsi_score, ret_score, asset):
    # Conservador: Renta Fija (letras, bonos) es lo óptimo. Penaliza fuertemente la volatilidad.
    if category == "letras":
        # Letras de tesoro en pesos (LECAPs). Muy seguras a corto/mediano plazo.
        return 90.0 + (asset.get("tna", 0.40) * 10.0)
    elif category == "bonos":
        # Bonos soberanos clásicos (ej: AL30, GD30). Tienen más volatilidad que las letras.
        # Regla cuantitativa: Para 6-12m priorizar duración modificada < 1.2 años
        maturity_str = asset.get("maturity", "2030-07-09")
        try:
            from datetime import datetime
            days_to_mat = (datetime.strptime(maturity_str, "%Y-%m-%d") - datetime.now()).days
            duration = days_to_mat / 365.25
        except Exception:
            duration = 4.0

        if duration > 1.2:
            # Penalización por riesgo de tasa/reestructuración a mediano plazo (Duration > 1.2)
            return 45.0 + (sharpe_score * 0.10)
            
        return 75.0 + (sharpe_score * 0.15)
    elif category == "cedears":
        # CEDEARs estables extranjeros. Solo permitimos a los que tengan muy baja volatilidad (ej: KO, PG)
        if volatility < 0.22:
            return 55.0 + (sharpe_score * 0.2)
        return 20.0
    elif category == "sp500":
        # Acciones defensivas directas del SP500
        if volatility < 0.20:
            return 60.0 + (sharpe_score * 0.20)
        return 30.0
    elif category == "merval":
        # Acciones locales: muy volátiles en pesos y dólares
        return 15.0
    elif category == "crypto":
        # Criptomonedas: vetadas del perfil conservador
        return 0.0
    return 0.0

def calculate_moderate_score(category, volatility, sharpe_score, rsi_score, ret_score):
    # Moderado: Mix equilibrado de CEDEARs, SP500, Letras y Bonos. Penaliza volatilidad extrema.
    base_category_scores = {
        "sp500": 75.0,
        "cedears": 72.0,
        "bonos": 65.0,
        "letras": 60.0,
        "merval": 50.0,
        "crypto": 45.0
    }
    
    base = base_category_scores.get(category, 0.0)
    
    # Penalización de volatilidad alta en moderado
    vol_penalty = max(0.0, (volatility - 0.25) * 80.0)
    
    # Ajuste por métricas cuantitativas
    score = base + (sharpe_score * 0.2) + (rsi_score * 0.15) + (ret_score * 0.1) - vol_penalty
    return max(0.0, min(95.0, score))

def calculate_aggressive_score(category, volatility, sharpe_score, rsi_score, ret_score):
    # Agresivo: Maximiza Momentum y Retorno. Renta variable de crecimiento (CEDEARs, SP500) y Cripto. No penaliza volatilidad alta, la valora si hay retorno.
    base_category_scores = {
        "crypto": 80.0,
        "sp500": 78.0,
        "merval": 75.0,
        "cedears": 75.0,
        "bonos": 60.0,
        "letras": 30.0
    }
    
    base = base_category_scores.get(category, 0.0)
    
    # Pondera más alto el Momentum bursátil (RSI óptimo y retornos rápidos)
    score = base + (ret_score * 0.35) + (rsi_score * 0.2) + (sharpe_score * 0.1)
    
    # Si la volatilidad es extremadamente baja (ej: letras a tasa fija), se penaliza en agresivo debido al bajo potencial de ganancia real.
    if volatility < 0.10:
        score -= 20.0
        
    return max(0.0, min(100.0, score))

def get_recommendations_by_profile(market_data, profile):
    """
    Ordena y retorna el top 10 general y agrupado por categorías para un perfil dado.
    """
    scored_assets = []
    for asset in market_data:
        score = score_asset_for_profile(asset, profile)
        scored_assets.append({
            **asset,
            "score": round(score, 1)
        })
        
    # Ordenar por puntaje descendente
    scored_assets.sort(key=lambda x: x["score"], reverse=True)
    
    # Top 10 General consolidado
    top_10 = scored_assets[:10]
    
    # Agrupación por categorías (Separación requerida por el usuario)
    grouped = {}
    categories_keys = ["merval", "cedears", "sp500", "letras", "bonos", "crypto"]
    for cat in categories_keys:
        cat_assets = [a for a in scored_assets if a["category"] == cat]
        # Top 5 para cada categoría individual
        grouped[cat] = cat_assets[:5]
        
    return {
        "profile": profile,
        "top_10": top_10,
        "categories": grouped
    }
