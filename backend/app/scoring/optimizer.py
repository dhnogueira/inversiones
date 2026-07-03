"""
Optimizador de Portafolios basado en la Teoría Moderna de Portafolios (Markowitz).
Calcula las ponderaciones óptimas de activos para maximizar el Ratio de Sharpe
a partir de la matriz de covarianza y los retornos esperados.
"""
import numpy as np
from scipy.optimize import minimize


def optimize_portfolio(assets, profile, risk_free_rate=0.40):
    """
    Calcula los pesos óptimos del portafolio usando frontera eficiente de Markowitz.
    
    Args:
        assets: Lista de activos con ret_12m y volatility
        profile: 'conservador', 'moderado', 'agresivo'
        risk_free_rate: Tasa libre de riesgo anual (default 40% para Argentina en pesos)
    
    Returns:
        dict con weights[], expected_return, expected_volatility, sharpe_ratio
    """
    if len(assets) < 2:
        # Con 1 solo activo, asignar 100%
        return {
            "weights": [{"ticker": a["ticker"], "name": a["name"], "category": a["category"], "weight": round(1.0 / len(assets), 4)} for a in assets],
            "expected_return": assets[0].get("ret_12m", 0) if assets else 0,
            "expected_volatility": assets[0].get("volatility", 0) if assets else 0,
            "sharpe_ratio": assets[0].get("sharpe", 0) if assets else 0
        }

    n = len(assets)
    
    # Extraer retornos esperados y volatilidades
    returns = np.array([a.get("ret_12m", a.get("tna", 0.0)) for a in assets])
    vols = np.array([a.get("volatility", 0.20) for a in assets])
    
    # Sanitizar NaN/Inf
    returns = np.nan_to_num(returns, nan=0.0, posinf=1.0, neginf=-1.0)
    vols = np.nan_to_num(vols, nan=0.20, posinf=1.0, neginf=0.01)
    vols = np.clip(vols, 0.01, 2.0)  # Evitar volatilidades cero
    
    # Construir matriz de covarianza sintética a partir de volatilidades
    # Usamos correlaciones estimadas por categoría
    cov_matrix = build_covariance_matrix(assets, vols)
    
    # Ajustar tasa libre de riesgo según moneda predominante
    currencies = [a.get("currency", "ARS") for a in assets]
    usd_count = currencies.count("USD")
    if usd_count > len(assets) / 2:
        risk_free_rate = 0.05  # US T-bills ~5%
    
    # Restricciones de peso según perfil
    bounds = get_weight_bounds(assets, profile)
    
    # Restricción: suma de pesos = 1
    constraints = [{'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}]
    
    # Optimización: maximizar Sharpe = minimizar -Sharpe
    initial_weights = np.array([1.0 / n] * n)
    
    def neg_sharpe(weights):
        port_return = np.dot(weights, returns)
        port_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
        if port_vol < 1e-8:
            return 0
        return -(port_return - risk_free_rate) / port_vol
    
    result = minimize(
        neg_sharpe,
        initial_weights,
        method='SLSQP',
        bounds=bounds,
        constraints=constraints,
        options={'maxiter': 1000, 'ftol': 1e-10}
    )
    
    if result.success:
        optimal_weights = result.x
    else:
        # Fallback: pesos iguales
        optimal_weights = initial_weights
    
    # Normalizar pesos pequeños a 0 y redistribuir
    optimal_weights = np.maximum(optimal_weights, 0)
    optimal_weights[optimal_weights < 0.02] = 0  # Eliminar posiciones < 2%
    weight_sum = np.sum(optimal_weights)
    if weight_sum > 0:
        optimal_weights = optimal_weights / weight_sum
    else:
        optimal_weights = initial_weights
    
    # Calcular métricas del portafolio óptimo
    port_return = float(np.dot(optimal_weights, returns))
    port_vol = float(np.sqrt(np.dot(optimal_weights.T, np.dot(cov_matrix, optimal_weights))))
    port_sharpe = (port_return - risk_free_rate) / port_vol if port_vol > 0 else 0
    
    # Construir respuesta con los activos que tienen peso > 0
    weight_items = []
    for i, asset in enumerate(assets):
        w = float(optimal_weights[i])
        if w > 0.005:  # Solo incluir activos con peso > 0.5%
            weight_items.append({
                "ticker": asset["ticker"],
                "name": asset["name"],
                "category": asset["category"],
                "currency": asset.get("currency", "ARS"),
                "weight": round(w, 4),
                "weight_pct": round(w * 100, 1)
            })
    
    # Ordenar por peso descendente
    weight_items.sort(key=lambda x: x["weight"], reverse=True)
    
    return {
        "weights": weight_items,
        "expected_return": round(port_return * 100, 2),
        "expected_volatility": round(port_vol * 100, 2),
        "sharpe_ratio": round(port_sharpe, 2),
        "profile": profile,
        "risk_free_rate": round(risk_free_rate * 100, 2)
    }


def build_covariance_matrix(assets, vols):
    """
    Construye una matriz de covarianza sintética usando correlaciones estimadas
    por categoría de activo. Los activos de la misma categoría tienen mayor correlación.
    """
    n = len(assets)
    categories = [a.get("category", "") for a in assets]
    
    # Matriz de correlación base
    corr = np.eye(n)
    
    for i in range(n):
        for j in range(i + 1, n):
            if categories[i] == categories[j]:
                # Misma categoría: correlación alta
                rho = 0.70
            elif _is_equity(categories[i]) and _is_equity(categories[j]):
                # Ambos renta variable: correlación moderada
                rho = 0.45
            elif _is_fixed_income(categories[i]) and _is_fixed_income(categories[j]):
                # Ambos renta fija: correlación moderada-alta
                rho = 0.55
            elif categories[i] == "crypto" or categories[j] == "crypto":
                # Cripto vs. cualquier otro: correlación baja
                rho = 0.20
            elif _is_equity(categories[i]) and _is_fixed_income(categories[j]):
                # Renta variable vs. fija: correlación baja-negativa
                rho = -0.10
            elif _is_fixed_income(categories[i]) and _is_equity(categories[j]):
                rho = -0.10
            else:
                rho = 0.25
            
            corr[i, j] = rho
            corr[j, i] = rho
    
    # Construir covarianza: Cov = D * Corr * D (donde D es diagonal de volatilidades)
    D = np.diag(vols)
    cov = D @ corr @ D
    
    # Asegurar que sea semi-definida positiva
    eigvals = np.linalg.eigvalsh(cov)
    if np.any(eigvals < 0):
        cov += np.eye(n) * (abs(min(eigvals)) + 1e-6)
    
    return cov


def get_weight_bounds(assets, profile):
    """
    Define los límites de peso por activo según el perfil de riesgo.
    """
    bounds = []
    for asset in assets:
        cat = asset.get("category", "")
        
        if profile == "conservador":
            if cat in ("letras", "bonos"):
                bounds.append((0.0, 0.40))
            elif cat in ("cedears", "sp500"):
                bounds.append((0.0, 0.15))
            elif cat == "merval":
                bounds.append((0.0, 0.05))
            elif cat == "crypto":
                bounds.append((0.0, 0.0))  # No cripto en conservador
            else:
                bounds.append((0.0, 0.10))
        
        elif profile == "moderado":
            if cat in ("letras", "bonos"):
                bounds.append((0.0, 0.30))
            elif cat in ("cedears", "sp500"):
                bounds.append((0.0, 0.25))
            elif cat == "merval":
                bounds.append((0.0, 0.15))
            elif cat == "crypto":
                bounds.append((0.0, 0.10))
            else:
                bounds.append((0.0, 0.20))
        
        elif profile == "agresivo":
            if cat in ("letras",):
                bounds.append((0.0, 0.05))
            elif cat == "bonos":
                bounds.append((0.0, 0.15))
            elif cat in ("cedears", "sp500", "merval"):
                bounds.append((0.0, 0.35))
            elif cat == "crypto":
                bounds.append((0.0, 0.30))
            else:
                bounds.append((0.0, 0.25))
        else:
            bounds.append((0.0, 0.30))
    
    return bounds


def _is_equity(cat):
    return cat in ("merval", "cedears", "sp500")


def _is_fixed_income(cat):
    return cat in ("letras", "bonos")
