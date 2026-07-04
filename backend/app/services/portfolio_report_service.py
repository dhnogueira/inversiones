"""
Motor de Informe Diario de Cartera.
Analiza las posiciones del usuario contra datos de mercado actuales y genera
un informe estructurado con recomendaciones por activo, factores de riesgo
y un veredicto global de la cartera.
"""
from datetime import datetime
from typing import List, Dict, Optional


# ─────────────────────────────────────────────────────────────────────────────
#  FACTORES DE RIESGO SISTÉMICO (Cisnes Negros y Contexto Global)
#  Actualizados al contexto de Julio 2026
# ─────────────────────────────────────────────────────────────────────────────

SYSTEMIC_RISK_FACTORS = [
    {
        "id": "arg_macro",
        "title": "Transición Macroeconómica Argentina",
        "icon": "fa-flag",
        "severity": "medium",
        "categories": ["merval", "cedears", "bonos", "letras"],
        "description": (
            "Argentina transita un proceso de estabilización con reducción gradual de la brecha cambiaria "
            "y ancla inflacionaria. El riesgo cambiario persiste ante posibles ajustes del tipo de cambio oficial. "
            "Los activos en ARS deben superar la inflación proyectada (~22% anual) para generar retorno real positivo. "
            "Monitorear: reservas del BCRA, balanza comercial y cumplimiento de metas con el FMI."
        ),
        "impact": "Exposición directa para activos denominados en ARS. Los bonos hard-dollar ofrecen cobertura."
    },
    {
        "id": "fed_policy",
        "title": "Política Monetaria de la Reserva Federal (EE.UU.)",
        "icon": "fa-university",
        "severity": "medium",
        "categories": ["sp500", "cedears", "crypto"],
        "description": (
            "La Fed mantiene tasas en niveles restrictivos para controlar la inflación remanente. "
            "Un pivot hacia tasas más bajas podría disparar el rally en renta variable y cripto, "
            "mientras que una postura hawkish más prolongada presionaría los múltiplos de valuación. "
            "El P/E del S&P 500 sobre su media histórica sugiere valuaciones exigentes."
        ),
        "impact": "Alta sensibilidad en tech/growth. Considerar duration de bonos USD ante cambios de tasas."
    },
    {
        "id": "crypto_regulation",
        "title": "Avance Regulatorio Global en Criptomonedas",
        "icon": "fa-bitcoin-sign",
        "severity": "high",
        "categories": ["crypto"],
        "description": (
            "Los reguladores de EE.UU., Europa y Asia avanzan en marcos normativos para exchanges y activos digitales. "
            "La aprobación de ETFs de BTC y ETH spot amplió la adopción institucional. "
            "El halving de Bitcoin (completado) históricamente precede ciclos alcistas de 12-18 meses. "
            "Riesgo: restricciones regulatorias abruptas o hackeos a exchanges mayores."
        ),
        "impact": "Volatilidad extrema posible. Mantener posición cripto dentro del límite de riesgo del perfil."
    },
    {
        "id": "geopolitical",
        "title": "Tensiones Geopolíticas y Riesgo de Cadena de Suministro",
        "icon": "fa-globe",
        "severity": "medium",
        "categories": ["sp500", "cedears", "merval", "crypto"],
        "description": (
            "Conflictos en Europa del Este y tensiones EE.UU.-China impactan cadenas de suministro globales "
            "y generan episodios de risk-off. Los commodities (petróleo, gas, minerales estratégicos) "
            "pueden verse afectados, impactando indirectamente a empresas de energía y materiales. "
            "El dólar como activo refugio puede apreciarse en contextos de alta incertidumbre."
        ),
        "impact": "Diversificación geográfica recomendada. Evitar alta concentración en un solo sector o región."
    },
    {
        "id": "black_swan_concentration",
        "title": "Riesgo de Concentración de Cartera",
        "icon": "fa-layer-group",
        "severity": "dynamic",  # se activa si una posición > 40% del portafolio
        "categories": ["all"],
        "description": (
            "Una cartera muy concentrada en un único activo o categoría amplifica la volatilidad total "
            "y expone al inversor a eventos idiosincráticos (resultados corporativos, regulación sectorial, "
            "insolvencia). La diversificación reduce el riesgo no sistémico sin sacrificar retorno esperado."
        ),
        "impact": "Se recomienda que ningún activo supere el 35% del portafolio total."
    }
]


# ─────────────────────────────────────────────────────────────────────────────
#  LÓGICA DE RECOMENDACIÓN POR ACTIVO
# ─────────────────────────────────────────────────────────────────────────────

def _determine_action(asset_data: dict, pnl_pct: float, profile: str) -> tuple[str, str, str]:
    """
    Determina la acción recomendada para un activo basado en indicadores técnicos,
    fundamentales, PnL actual y perfil del inversor.

    Returns: (action, color, rationale)
    """
    rsi = asset_data.get("rsi", 50.0)
    sharpe = asset_data.get("sharpe", 0.0)
    score = asset_data.get("score", 50.0)
    volatility = asset_data.get("volatility", 0.25)
    trend = asset_data.get("trend", "Estable")
    ret_1m = asset_data.get("ret_1m", 0.0)
    category = asset_data.get("category", "")
    tna = asset_data.get("tna", 0.0)

    reasons = []

    # --- VENDER TOTAL ---
    # Condición: score muy bajo O (RSI sobrecompra extrema + PnL alto + sharpe negativo)
    if score < 25:
        reasons.append(f"Score muy bajo ({score:.0f}/100) para el perfil {profile}.")
        reasons.append("El activo no cumple criterios mínimos de riesgo/retorno.")
        return "VENDER TOTAL", "danger", " ".join(reasons)

    if rsi > 78 and pnl_pct > 20 and sharpe < 0.2:
        reasons.append(f"RSI en zona de sobrecompra extrema ({rsi:.0f}) con ganancia acumulada de {pnl_pct:+.1f}%.")
        reasons.append("Se recomienda tomar ganancias antes de una corrección técnica.")
        return "VENDER TOTAL", "danger", " ".join(reasons)

    if "Bajista" in trend and sharpe < 0 and pnl_pct < -15:
        reasons.append(f"Tendencia bajista confirmada con pérdida acumulada de {pnl_pct:.1f}%.")
        reasons.append("El ratio Sharpe negativo indica que el riesgo no está siendo recompensado.")
        return "VENDER TOTAL", "danger", " ".join(reasons)

    # --- VENDER PARCIAL ---
    if rsi > 70 and pnl_pct > 12:
        reasons.append(f"RSI en sobrecompra ({rsi:.0f}) con posición en ganancias ({pnl_pct:+.1f}%).")
        reasons.append("Reducir posición parcialmente para asegurar ganancias y liberar liquidez.")
        return "VENDER PARCIAL", "warning", " ".join(reasons)

    if score < 45 and "Bajista" in trend:
        reasons.append(f"Score moderado-bajo ({score:.0f}/100) con tendencia bajista.")
        reasons.append("Considerar reducción de exposición hasta que la tendencia se revierta.")
        return "VENDER PARCIAL", "warning", " ".join(reasons)

    if profile == "conservador" and volatility > 0.35 and category not in ("letras", "bonos"):
        reasons.append(f"Volatilidad elevada ({volatility*100:.0f}%) incompatible con perfil conservador.")
        reasons.append("Rebalancear hacia instrumentos de menor riesgo (letras/bonos ARS o USD).")
        return "VENDER PARCIAL", "warning", " ".join(reasons)

    # Para renta fija conservadora: advertir si la TNA es muy baja
    if category in ("letras", "bonos") and tna > 0 and tna < 0.18 and profile == "conservador":
        reasons.append(f"TNA del {tna*100:.1f}% insuficiente para superar inflación proyectada (~22%).")
        reasons.append("Evaluar rotar hacia instrumentos con mejor rendimiento real.")
        return "VENDER PARCIAL", "warning", " ".join(reasons)

    # --- INCREMENTAR ---
    if rsi < 42 and sharpe > 0.7 and score > 72 and pnl_pct > -5:
        reasons.append(f"RSI en zona de sobreventa relativa ({rsi:.0f}) con fundamentos sólidos (score {score:.0f}/100, Sharpe {sharpe:.2f}).")
        reasons.append("El activo ofrece oportunidad de acumulación en zona técnica favorable.")
        return "INCREMENTAR", "success", " ".join(reasons)

    if ret_1m > 0.04 and trend == "Alcista" and score > 75:
        reasons.append(f"Momentum mensual positivo ({ret_1m*100:+.1f}%) con tendencia alcista y score alto.")
        reasons.append("Las condiciones técnicas y fundamentales justifican aumentar la posición.")
        return "INCREMENTAR", "success", " ".join(reasons)

    # --- MANTENER (default) ---
    if pnl_pct > 0:
        reasons.append(f"Posición rentable ({pnl_pct:+.1f}%) sin señales técnicas extremas de salida.")
    else:
        reasons.append(f"Posición en leve pérdida ({pnl_pct:+.1f}%) pero sin señal técnica de cierre.")

    if score >= 60:
        reasons.append(f"Score {score:.0f}/100 indica un activo dentro de los rangos aceptables para el perfil {profile}.")
    else:
        reasons.append("Monitorear de cerca ante posible deterioro adicional de indicadores.")

    return "MANTENER", "neutral", " ".join(reasons)


def _get_risk_flags(asset_data: dict, pnl_pct: float, weight_pct: float) -> List[str]:
    """Retorna lista de flags de riesgo específicos para el activo."""
    flags = []
    rsi = asset_data.get("rsi", 50.0)
    volatility = asset_data.get("volatility", 0.25)
    sharpe = asset_data.get("sharpe", 0.0)
    category = asset_data.get("category", "")

    if rsi > 72:
        flags.append(f"⚠ RSI sobrecompra ({rsi:.0f})")
    if rsi < 28:
        flags.append(f"⚠ RSI sobreventa ({rsi:.0f})")
    if volatility > 0.50:
        flags.append(f"🔥 Volatilidad extrema ({volatility*100:.0f}%)")
    if sharpe < 0:
        flags.append("📉 Sharpe negativo — riesgo no recompensado")
    if weight_pct > 35:
        flags.append(f"⚡ Alta concentración ({weight_pct:.0f}% del portafolio)")
    if pnl_pct < -20:
        flags.append(f"🔴 Drawdown significativo ({pnl_pct:.1f}%)")
    if pnl_pct > 30:
        flags.append(f"💰 Ganancia elevada — considerar toma de ganancias parcial")
    if category == "crypto" and volatility > 0.60:
        flags.append("₿ Riesgo cripto elevado — posición especulativa")

    return flags


def _get_category_pnl_breakdown(positions_with_pnl: List[dict]) -> List[dict]:
    """Agrupa el P&L por categoría para el breakdown."""
    cat_map: Dict[str, dict] = {}
    for pos in positions_with_pnl:
        cat = pos.get("category", "otros")
        if cat not in cat_map:
            cat_map[cat] = {"invested": 0.0, "current": 0.0, "count": 0}
        cat_map[cat]["invested"] += pos.get("invested", 0.0)
        cat_map[cat]["current"] += pos.get("current_value", 0.0)
        cat_map[cat]["count"] += 1

    breakdown = []
    for cat, data in cat_map.items():
        invested = data["invested"]
        current = data["current"]
        pnl = current - invested
        pnl_pct = (pnl / invested * 100) if invested > 0 else 0
        breakdown.append({
            "category": cat,
            "invested": round(invested, 2),
            "current_value": round(current, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "count": data["count"]
        })
    return sorted(breakdown, key=lambda x: x["pnl_pct"], reverse=True)


def _determine_overall_action(positions_analysis: List[dict], total_pnl_pct: float) -> tuple[str, str]:
    """Determina la acción global de la cartera."""
    sell_total = sum(1 for p in positions_analysis if p["recommendation"] == "VENDER TOTAL")
    sell_partial = sum(1 for p in positions_analysis if p["recommendation"] == "VENDER PARCIAL")
    increase = sum(1 for p in positions_analysis if p["recommendation"] == "INCREMENTAR")
    total = len(positions_analysis)

    if total == 0:
        return "SIN POSICIONES", "La cartera está vacía. Usar las recomendaciones del dashboard para construir una posición inicial."

    sell_ratio = (sell_total + sell_partial) / total

    if sell_total >= 2 or sell_ratio > 0.6:
        return "REBALANCEAR", (
            f"La mayoría de las posiciones presentan señales de salida. "
            f"Se recomienda rebalancear la cartera tomando ganancias o reduciendo exposición "
            f"y rotando hacia activos con mejor perfil de riesgo/retorno según el dashboard."
        )
    if total_pnl_pct > 15 and sell_partial > 0:
        return "PROTEGER GANANCIAS", (
            f"La cartera acumula una ganancia del {total_pnl_pct:+.1f}%. "
            f"Se recomienda asegurar parte de las ganancias reduciendo posiciones con señal de venta parcial "
            f"y manteniendo las posiciones con mejor ratio riesgo/retorno."
        )
    if increase >= 2 and total_pnl_pct >= 0:
        return "OPORTUNIDAD DE ACUMULACIÓN", (
            f"Múltiples activos muestran condiciones técnicas favorables para incrementar posición. "
            f"La cartera tiene un desempeño positivo ({total_pnl_pct:+.1f}%). "
            f"Aprovechar zonas de precio favorables en los activos señalados."
        )

    return "MANTENER Y MONITOREAR", (
        f"La cartera está en equilibrio razonable (P&L: {total_pnl_pct:+.1f}%). "
        f"No hay señales extremas de entrada o salida. Continuar monitoreando los indicadores técnicos "
        f"y ajustar ante cambios en el contexto macroeconómico."
    )


# ─────────────────────────────────────────────────────────────────────────────
#  GENERADOR PRINCIPAL DEL INFORME
# ─────────────────────────────────────────────────────────────────────────────

def generate_portfolio_report(
    positions_with_pnl: List[dict],
    all_assets: List[dict],
    profile: str = "moderado",
    horizon: str = "medium"
) -> dict:
    """
    Genera el informe diario completo de la cartera.

    Args:
        positions_with_pnl: Lista de posiciones ya enriquecidas con P&L (output de calculate_portfolio_pnl).
        all_assets: Todos los activos del mercado (para obtener indicadores técnicos).
        profile: Perfil del inversor ('conservador', 'moderado', 'agresivo').
        horizon: Horizonte temporal ('short', 'medium', 'long').

    Returns:
        Dict con el informe completo estructurado.
    """
    # Índice de activos por ticker para lookup O(1)
    asset_index = {a["ticker"]: a for a in all_assets}

    # Total invertido para calcular pesos
    total_invested = sum(p.get("invested", 0.0) for p in positions_with_pnl)
    total_current = sum(p.get("current_value", 0.0) for p in positions_with_pnl)
    total_pnl = total_current - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0.0

    # Categorías presentes en la cartera
    categories_in_portfolio = set(p.get("category", "") for p in positions_with_pnl)

    # ── Análisis por posición ──
    positions_analysis = []
    for pos in positions_with_pnl:
        ticker = pos.get("ticker", "")
        pnl_pct = pos.get("pnl_pct", 0.0)
        invested = pos.get("invested", 0.0)
        weight_pct = (invested / total_invested * 100) if total_invested > 0 else 0.0

        # Obtener datos de mercado del activo (puede no existir si es un activo manual)
        asset_data = asset_index.get(ticker, {
            "rsi": 50.0, "sharpe": 0.5, "score": 50.0,
            "volatility": 0.25, "trend": "Estable",
            "ret_1m": 0.0, "category": pos.get("category", ""),
            "tna": pos.get("tna", 0.0)
        })
        # Asegurar que el score esté disponible si viene del endpoint de recomendaciones
        if "score" not in asset_data:
            asset_data["score"] = 50.0

        action, color, rationale = _determine_action(asset_data, pnl_pct, profile)
        risk_flags = _get_risk_flags(asset_data, pnl_pct, weight_pct)

        positions_analysis.append({
            "ticker": ticker,
            "name": pos.get("name", ticker),
            "category": pos.get("category", ""),
            "currency": pos.get("currency", "ARS"),
            "entry_price": pos.get("entry_price", 0.0),
            "current_price": pos.get("current_price", 0.0),
            "quantity": pos.get("quantity", 0.0),
            "invested": round(invested, 2),
            "current_value": round(pos.get("current_value", 0.0), 2),
            "pnl": round(pos.get("pnl", 0.0), 2),
            "pnl_pct": round(pnl_pct, 2),
            "weight_pct": round(weight_pct, 1),
            "recommendation": action,
            "recommendation_color": color,
            "rationale": rationale,
            "risk_flags": risk_flags,
            "technical_snapshot": {
                "rsi": round(asset_data.get("rsi", 50.0), 1),
                "sharpe": round(asset_data.get("sharpe", 0.0), 2),
                "volatility_pct": round(asset_data.get("volatility", 0.25) * 100, 1),
                "trend": asset_data.get("trend", "Estable"),
                "score": asset_data.get("score", 50.0),
                "ret_1m_pct": round(asset_data.get("ret_1m", 0.0) * 100, 2)
            }
        })

    # Ordenar por urgencia: VENDER TOTAL > VENDER PARCIAL > INCREMENTAR > MANTENER
    priority_order = {"VENDER TOTAL": 0, "VENDER PARCIAL": 1, "INCREMENTAR": 2, "MANTENER": 3}
    positions_analysis.sort(key=lambda x: priority_order.get(x["recommendation"], 3))

    # ── Contexto macro (por categorías presentes) ──
    market_context = []
    for factor in SYSTEMIC_RISK_FACTORS:
        factor_cats = factor["categories"]
        if "all" in factor_cats or any(c in categories_in_portfolio for c in factor_cats):
            # Para el factor de concentración, solo incluir si alguna posición supera el 35%
            if factor["id"] == "black_swan_concentration":
                max_weight = max((p["weight_pct"] for p in positions_analysis), default=0)
                if max_weight <= 35:
                    continue
            market_context.append({
                "title": factor["title"],
                "icon": factor["icon"],
                "severity": factor["severity"],
                "description": factor["description"],
                "impact": factor["impact"]
            })

    # ── Breakdown por categoría ──
    category_breakdown = _get_category_pnl_breakdown(positions_with_pnl)

    # ── Acción global ──
    overall_action, overall_rationale = _determine_overall_action(positions_analysis, total_pnl_pct)

    return {
        "generated_at": datetime.now().isoformat(),
        "profile": profile,
        "horizon": horizon,
        "summary": {
            "total_invested": round(total_invested, 2),
            "total_current": round(total_current, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "positions_count": len(positions_with_pnl)
        },
        "overall_action": overall_action,
        "overall_rationale": overall_rationale,
        "positions_analysis": positions_analysis,
        "category_breakdown": category_breakdown,
        "market_context": market_context,
    }
