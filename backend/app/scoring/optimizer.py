"""
Optimizador de Portafolios basado en la Teoría Moderna de Portafolios (Markowitz).
Calcula las ponderaciones óptimas de activos para maximizar el Ratio de Sharpe
a partir de la matriz de covarianza y los retornos esperados **en pesos argentinos**.

Corrección crítica: los retornos de todos los activos se convierten a ARS antes
de la optimización, lo que permite comparar manzanas con manzanas (activos en USD
vs activos en ARS) y garantizar que la asignación óptima supere la inflación.
"""
import numpy as np
from scipy.optimize import minimize
from app.scoring.profiles import (
    estimate_expected_return_ars,
    get_horizon_inflation,
    HORIZON_MEDIUM,
    PROJECTED_ARG_INFLATION,
)


def optimize_portfolio(assets, profile, horizon=HORIZON_MEDIUM, risk_free_rate=None):
    """
    Calcula los pesos óptimos del portafolio usando frontera eficiente de Markowitz.

    IMPORTANTE: Los retornos esperados se calculan todos en ARS usando la función
    `estimate_expected_return_ars`, que incorpora la devaluación del peso para
    activos en USD. Esto garantiza comparabilidad y que el retorno proyectado
    sea coherente con la realidad del inversor argentino.

    Args:
        assets:          Lista de activos con ret_12m, volatility, tna, category, currency.
        profile:         'conservador', 'moderado', 'agresivo'
        horizon:         'short', 'medium', 'long' – afecta proyecciones de retorno e inflación.
        risk_free_rate:  Tasa de referencia anual (default = inflación esperada del horizonte).

    Returns:
        dict con weights[], expected_return (%), expected_volatility (%), sharpe_ratio,
        inflation_reference (%), beats_inflation (bool).
    """
    if not assets:
        return {
            "weights": [],
            "expected_return": 0,
            "expected_volatility": 0,
            "sharpe_ratio": 0,
            "inflation_reference": round(get_horizon_inflation(horizon) * 100, 1),
            "beats_inflation": False
        }

    if len(assets) == 1:
        a = assets[0]
        ars_ret = estimate_expected_return_ars(a, profile, horizon)
        h_inf = get_horizon_inflation(horizon)
        return {
            "weights": [{"ticker": a["ticker"], "name": a["name"], "category": a["category"], "weight": 1.0, "weight_pct": 100.0}],
            "expected_return": round(ars_ret * 100, 2),
            "expected_volatility": round(a.get("volatility", 0.20) * 100, 2),
            "sharpe_ratio": round((ars_ret - h_inf) / max(0.01, a.get("volatility", 0.20)), 2),
            "inflation_reference": round(h_inf * 100, 1),
            "beats_inflation": ars_ret > h_inf
        }

    n = len(assets)
    horizon_inflation = get_horizon_inflation(horizon)

    # ---- Tasa libre de riesgo = inflación del horizonte ----
    # Utilizamos la inflación como benchmark mínimo de retorno real.
    # Si el activo/portafolio no supera la inflación, el Sharpe real es negativo.
    if risk_free_rate is None:
        risk_free_rate = horizon_inflation

    # ---- Retornos esperados en ARS para cada activo ----
    ars_returns = []
    for a in assets:
        r = estimate_expected_return_ars(a, profile, horizon)
        r = np.clip(r, -0.80, 5.0)   # limitar outliers extremos
        ars_returns.append(r)
    returns = np.array(ars_returns)

    # ---- Volatilidades ----
    vols = np.array([a.get("volatility", 0.20) for a in assets])
    vols = np.nan_to_num(vols, nan=0.20, posinf=1.0, neginf=0.01)
    vols = np.clip(vols, 0.01, 2.0)

    # Sanitizar retornos
    returns = np.nan_to_num(returns, nan=0.0, posinf=3.0, neginf=-0.80)

    # ---- Matriz de covarianza ----
    cov_matrix = build_covariance_matrix(assets, vols)

    # ---- Restricciones de peso según perfil y horizonte ----
    bounds = get_weight_bounds(assets, profile, horizon)

    # Validar si se permite asignar fondos a esta categoría (evitar que SLSQP falle por cotas cero)
    max_allocatable = sum(hi for lo, hi in bounds)
    if max_allocatable < 0.01:
        return {
            "weights": [],
            "expected_return": 0.0,
            "expected_volatility": 0.0,
            "sharpe_ratio": 0.0,
            "profile": profile,
            "horizon": horizon,
            "risk_free_rate": round(risk_free_rate * 100, 2),
            "inflation_reference": round(horizon_inflation * 100, 1),
            "beats_inflation": False,
            "spread_vs_inflation": 0.0,
            "message": "Ningún activo de esta categoría está permitido para tu perfil de riesgo y horizonte seleccionado."
        }


    # Restricción suma de pesos = 1
    constraints = [{'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}]

    # Restricción blanda: el retorno esperado del portafolio >= inflación + 2%
    # (Garantizamos que la solución Markowitz no converja en un mínimo que pierda contra inflación)
    min_required_return = horizon_inflation + 0.02
    constraints.append({
        'type': 'ineq',
        'fun': lambda w: np.dot(w, returns) - min_required_return
    })

    initial_weights = np.array([1.0 / n] * n)

    def neg_sharpe(weights):
        port_return = np.dot(weights, returns)
        port_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
        if port_vol < 1e-8:
            return 0
        return -(port_return - risk_free_rate) / port_vol

    # Primer intento: con restricción de retorno mínimo
    result = minimize(
        neg_sharpe,
        initial_weights,
        method='SLSQP',
        bounds=bounds,
        constraints=constraints,
        options={'maxiter': 2000, 'ftol': 1e-12}
    )

    if not result.success:
        # Segundo intento: sin restricción de retorno mínimo (fallback Sharpe puro)
        constraints_fallback = [{'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}]
        result = minimize(
            neg_sharpe,
            initial_weights,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints_fallback,
            options={'maxiter': 2000, 'ftol': 1e-10}
        )

    if result.success:
        optimal_weights = result.x
    else:
        # Último fallback: pesos proporcionales al retorno ARS
        positive_returns = np.maximum(returns, 0.01)
        optimal_weights = positive_returns / positive_returns.sum()

    # ---- Limpieza de pesos ----
    optimal_weights = np.maximum(optimal_weights, 0)
    optimal_weights[optimal_weights < 0.02] = 0
    weight_sum = np.sum(optimal_weights)
    if weight_sum > 0:
        optimal_weights = optimal_weights / weight_sum
    else:
        optimal_weights = initial_weights

    # ---- Métricas del portafolio ----
    port_return_ars = float(np.dot(optimal_weights, returns))
    port_vol = float(np.sqrt(np.dot(optimal_weights.T, np.dot(cov_matrix, optimal_weights))))

    # El Sharpe real: exceso de retorno sobre inflación / volatilidad
    port_sharpe = (port_return_ars - horizon_inflation) / port_vol if port_vol > 0 else 0

    beats_inflation = port_return_ars > horizon_inflation
    spread_vs_inflation = port_return_ars - horizon_inflation

    # ---- Construir respuesta ----
    weight_items = []
    for i, asset in enumerate(assets):
        w = float(optimal_weights[i])
        if w > 0.005:
            weight_items.append({
                "ticker": asset["ticker"],
                "name": asset["name"],
                "category": asset["category"],
                "currency": asset.get("currency", "ARS"),
                "weight": round(w, 4),
                "weight_pct": round(w * 100, 1),
                "ars_return_est": round(ars_returns[i] * 100, 1)
            })

    weight_items.sort(key=lambda x: x["weight"], reverse=True)

    return {
        "weights": weight_items,
        "expected_return": round(port_return_ars * 100, 2),
        "expected_volatility": round(port_vol * 100, 2),
        "sharpe_ratio": round(port_sharpe, 2),
        "profile": profile,
        "horizon": horizon,
        "risk_free_rate": round(risk_free_rate * 100, 2),
        "inflation_reference": round(horizon_inflation * 100, 1),
        "beats_inflation": beats_inflation,
        "spread_vs_inflation": round(spread_vs_inflation * 100, 1),
    }


def build_covariance_matrix(assets, vols):
    """
    Construye una matriz de covarianza sintética usando correlaciones estimadas
    por categoría de activo. Los activos de la misma categoría tienen mayor correlación.
    """
    n = len(assets)
    categories = [a.get("category", "") for a in assets]

    corr = np.eye(n)

    for i in range(n):
        for j in range(i + 1, n):
            if categories[i] == categories[j]:
                rho = 0.70
            elif _is_equity(categories[i]) and _is_equity(categories[j]):
                rho = 0.45
            elif _is_fixed_income(categories[i]) and _is_fixed_income(categories[j]):
                rho = 0.55
            elif categories[i] == "crypto" or categories[j] == "crypto":
                rho = 0.20
            elif _is_equity(categories[i]) and _is_fixed_income(categories[j]):
                rho = -0.10
            elif _is_fixed_income(categories[i]) and _is_equity(categories[j]):
                rho = -0.10
            else:
                rho = 0.25

            corr[i, j] = rho
            corr[j, i] = rho

    D = np.diag(vols)
    cov = D @ corr @ D

    eigvals = np.linalg.eigvalsh(cov)
    if np.any(eigvals < 0):
        cov += np.eye(n) * (abs(min(eigvals)) + 1e-6)

    return cov


def get_weight_bounds(assets, profile, horizon="medium"):
    """
    Define los límites de peso por activo según perfil Y horizonte temporal.
    Basado en la SKILL de Optimización de Cartera con ajustes por horizonte.
    """

    # Tabla de bounds: _BOUNDS[profile][horizon][category] = (min, max)
    _BOUNDS = {
        "conservador": {
            "short": {
                "letras":  (0.10, 0.50),  # Letras: core en corto plazo conservador
                "bonos":   (0.05, 0.40),
                "cedears": (0.0, 0.20),
                "sp500":   (0.0, 0.15),
                "merval":  (0.0, 0.0),
                "crypto":  (0.0, 0.0),
            },
            "medium": {
                "letras":  (0.0, 0.35),
                "bonos":   (0.05, 0.40),
                "cedears": (0.0, 0.30),
                "sp500":   (0.0, 0.30),
                "merval":  (0.0, 0.05),
                "crypto":  (0.0, 0.0),
            },
            "long": {
                "letras":  (0.0, 0.0),    # Sin letras en largo plazo
                "bonos":   (0.0, 0.25),
                "cedears": (0.05, 0.40),  # Cobertura cambiaria
                "sp500":   (0.05, 0.45),  # Crecimiento defensivo dolarizado
                "merval":  (0.0, 0.10),
                "crypto":  (0.0, 0.0),
            },
        },
        "moderado": {
            "short": {
                "letras":  (0.05, 0.35),
                "bonos":   (0.0, 0.30),
                "cedears": (0.0, 0.30),
                "sp500":   (0.0, 0.25),
                "merval":  (0.0, 0.15),
                "crypto":  (0.0, 0.10),
            },
            "medium": {
                "letras":  (0.0, 0.20),
                "bonos":   (0.0, 0.25),
                "cedears": (0.05, 0.35),
                "sp500":   (0.05, 0.35),
                "merval":  (0.0, 0.15),
                "crypto":  (0.0, 0.10),
            },
            "long": {
                "letras":  (0.0, 0.0),
                "bonos":   (0.0, 0.20),
                "cedears": (0.05, 0.35),
                "sp500":   (0.10, 0.40),
                "merval":  (0.0, 0.20),
                "crypto":  (0.0, 0.15),
            },
        },
        "agresivo": {
            "short": {
                "letras":  (0.0, 0.10),
                "bonos":   (0.0, 0.10),
                "cedears": (0.0, 0.30),
                "sp500":   (0.0, 0.25),
                "merval":  (0.05, 0.35),  # Merval momentum corto agresivo
                "crypto":  (0.05, 0.35),  # Crypto momentum corto agresivo
            },
            "medium": {
                "letras":  (0.0, 0.05),
                "bonos":   (0.0, 0.15),
                "cedears": (0.05, 0.35),
                "sp500":   (0.05, 0.35),
                "merval":  (0.0, 0.25),
                "crypto":  (0.0, 0.20),
            },
            "long": {
                "letras":  (0.0, 0.0),
                "bonos":   (0.0, 0.10),
                "cedears": (0.05, 0.30),
                "sp500":   (0.10, 0.40),
                "merval":  (0.0, 0.25),
                "crypto":  (0.05, 0.30),
            },
        },
    }

    bounds_table = _BOUNDS.get(profile, _BOUNDS["moderado"]).get(horizon, _BOUNDS["moderado"]["medium"])

    bounds = []
    for asset in assets:
        cat = asset.get("category", "")
        lo, hi = bounds_table.get(cat, (0.0, 0.25))
        bounds.append((lo, hi))

    return bounds


def _is_equity(cat):
    return cat in ("merval", "cedears", "sp500")


def _is_fixed_income(cat):
    return cat in ("letras", "bonos")
