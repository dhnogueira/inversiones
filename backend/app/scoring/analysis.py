import numpy as np
from app.scoring.profiles import estimate_expected_return_ars, PROJECTED_ARG_INFLATION


def calculate_tp_sl(price, volatility, profile, category):
    """
    Calcula dinámicamente el Take Profit y Stop Loss sugeridos
    según la volatilidad del activo y el perfil de riesgo seleccionado.
    """
    vol = max(0.04, min(0.60, volatility))
    if category in ("letras", "bonos"):
        # Renta Fija
        if profile == "conservador":
            tp_pct, sl_pct = 0.04, 0.02
        elif profile == "moderado":
            tp_pct, sl_pct = 0.08, 0.04
        else: # agresivo
            tp_pct, sl_pct = 0.15, 0.07
    else:
        # Renta Variable / Cripto
        if profile == "conservador":
            tp_pct, sl_pct = max(0.06, vol * 0.8), max(0.03, vol * 0.4)
        elif profile == "moderado":
            tp_pct, sl_pct = max(0.12, vol * 1.2), max(0.06, vol * 0.6)
        else: # agresivo
            tp_pct, sl_pct = max(0.25, vol * 1.8), max(0.12, vol * 0.9)
            
    tp = price * (1.0 + tp_pct)
    sl = price * (1.0 - sl_pct)
    return round(tp, 2), round(sl, 2), round(tp_pct * 100, 1), round(sl_pct * 100, 1)


def build_volume_level_analysis(price, support, resistance, volume_cluster, currency):
    """
    Construye la narrativa técnica de soporte, resistencia y cluster de volumen (POC).
    """
    content = (
        f"El análisis de la estructura de precios ubica los niveles clave del activo:\n"
        f"- **Soporte de mediano plazo:** {currency} {support:,.2f} (zona histórica de compra).\n"
        f"- **Resistencia de largo plazo:** {currency} {resistance:,.2f} (zona histórica de toma de ganancias).\n"
        f"- **Precio Clave del Volumen (POC):** {currency} {volume_cluster:,.2f}. Este nivel representa "
        f"el precio más operado del trimestre, operando como un pivote de estabilidad de volumen."
    )
    return {
        "title": "Estructura de Precios (Soporte/Resistencia/Volumen)",
        "icon": "fa-chart-area",
        "content": content,
        "value": f"POC: {volume_cluster:,.2f}",
        "status": "success" if price >= volume_cluster else "neutral"
    }


def generate_asset_analysis(asset, profile):
    """
    Genera un análisis detallado para un activo, incluyendo:
    - Análisis Técnico (RSI, EMAs, Tendencia, Volatilidad, Soportes, Resistencias, POC)
    - Análisis Fundamental / de Rendimiento (Sharpe, Inflación esperada)
    - Contexto Macroeconómico
    - Veredicto final (Comprar / Mantener / Evitar con TP, SL e inflación)
    """
    category = asset.get("category", "")
    ticker = asset.get("ticker", "")
    name = asset.get("name", ticker)
    price = asset.get("price", 0)
    currency = asset.get("currency", "ARS")
    volatility = asset.get("volatility", 0.30)
    sharpe = asset.get("sharpe", 0.0)
    rsi = asset.get("rsi", 50.0)
    ret_1m = asset.get("ret_1m", 0.0)
    ret_3m = asset.get("ret_3m", 0.0)
    ret_6m = asset.get("ret_6m", 0.0)
    ret_12m = asset.get("ret_12m", 0.0)
    trend = asset.get("trend", "Estable")
    score = asset.get("score", 0.0)
    ema_50 = asset.get("ema_50", 0)
    ema_200 = asset.get("ema_200", 0)
    tna = asset.get("tna", None)
    maturity = asset.get("maturity", None)
    
    # Soporte, resistencia, POC
    support = asset.get("support", round(price * 0.90, 2))
    resistance = asset.get("resistance", round(price * 1.10, 2))
    volume_cluster = asset.get("volume_cluster", round(price * 0.98, 2))

    # Sanitizar NaN / Inf
    for var_name in ['volatility', 'sharpe', 'rsi', 'ret_1m', 'ret_3m', 'ret_6m', 'ret_12m']:
        val = locals()[var_name]
        if isinstance(val, float) and (np.isnan(val) or np.isinf(val)):
            locals()[var_name] = 0.0

    # ------- Sección 1: Análisis Técnico -------
    technical = build_technical_analysis(price, rsi, ema_50, ema_200, volatility, trend, ret_1m, ret_3m, category)
    # Agregar análisis de soporte, resistencia y POC
    technical.append(build_volume_level_analysis(price, support, resistance, volume_cluster, currency))

    # ------- Sección 2: Análisis Fundamental / Rendimiento -------
    fundamental = build_fundamental_analysis(category, sharpe, ret_6m, ret_12m, tna, maturity, volatility, currency)

    # ------- Sección 3: Contexto Macroeconómico -------
    macro = build_macro_context(category, currency, profile)

    # ------- Sección 4: Veredicto Final -------
    tp, sl, tp_pct, sl_pct = calculate_tp_sl(price, volatility, profile, category)
    verdict = build_verdict(score, profile, category, trend, sharpe, rsi, volatility)
    verdict["take_profit"] = tp
    verdict["stop_loss"] = sl
    verdict["tp_pct"] = tp_pct
    verdict["sl_pct"] = sl_pct

    return {
        "ticker": ticker,
        "name": name,
        "category": category,
        "price": price,
        "currency": currency,
        "score": score,
        "profile": profile,
        "technical": technical,
        "fundamental": fundamental,
        "macro": macro,
        "verdict": verdict,
        "support": support,
        "resistance": resistance,
        "volume_cluster": volume_cluster,
        "take_profit": tp,
        "stop_loss": sl,
        "tp_pct": tp_pct,
        "sl_pct": sl_pct
    }


def build_technical_analysis(price, rsi, ema_50, ema_200, volatility, trend, ret_1m, ret_3m, category):
    sections = []

    # RSI Interpretation
    if rsi > 70:
        rsi_text = f"El RSI de 14 períodos se encuentra en {rsi:.1f}, lo que indica una zona de **sobrecompra**. Históricamente, un RSI por encima de 70 sugiere que el activo podría experimentar una corrección a la baja en el corto plazo. Se recomienda cautela para nuevas entradas."
    elif rsi < 30:
        rsi_text = f"El RSI de 14 períodos se encuentra en {rsi:.1f}, señalando una condición de **sobreventa**. Esto puede representar una oportunidad de entrada si los fundamentos acompañan, ya que el activo podría estar subvaluado técnicamente."
    elif 50 <= rsi <= 65:
        rsi_text = f"El RSI de 14 períodos está en {rsi:.1f}, situado en una zona de **momentum alcista moderado**. Este es el rango ideal para inversiones de mediano plazo (6-12 meses), ya que indica fuerza de tendencia sin agotamiento."
    else:
        rsi_text = f"El RSI de 14 períodos se encuentra en {rsi:.1f}, en una zona **neutral**. No hay señales claras de sobrecompra ni sobreventa. El activo está en equilibrio entre oferta y demanda."

    sections.append({
        "title": "RSI (Índice de Fuerza Relativa)",
        "icon": "fa-gauge-high",
        "content": rsi_text,
        "value": f"{rsi:.1f}",
        "status": "warning" if rsi > 70 or rsi < 30 else "success" if 50 <= rsi <= 65 else "neutral"
    })

    # EMA Cross Analysis
    if ema_50 and ema_200 and ema_50 > 0 and ema_200 > 0:
        if ema_50 > ema_200 and price > ema_50:
            ema_text = f"La EMA de 50 días ({ema_50:.2f}) se encuentra por encima de la EMA de 200 días ({ema_200:.2f}), y el precio actual ({price:.2f}) supera ambas medias. Esta configuración se denomina **Golden Cross activo** y es una señal técnica fuertemente alcista para el mediano plazo."
            ema_status = "success"
        elif ema_50 < ema_200 and price < ema_50:
            ema_text = f"La EMA de 50 días ({ema_50:.2f}) se encuentra por debajo de la EMA de 200 días ({ema_200:.2f}), y el precio ({price:.2f}) cotiza por debajo de ambas. Esta configuración se conoce como **Death Cross** y es una señal de debilidad técnica persistente."
            ema_status = "danger"
        elif price > ema_200:
            ema_text = f"El precio ({price:.2f}) se mantiene por encima de la EMA de 200 días ({ema_200:.2f}), lo que indica que la tendencia de largo plazo sigue siendo **alcista**. Sin embargo, la EMA de 50 días ({ema_50:.2f}) aún no confirma un cruce definitivo."
            ema_status = "neutral"
        else:
            ema_text = f"El precio ({price:.2f}) cotiza por debajo de la EMA de 200 días ({ema_200:.2f}), lo que sugiere que la tendencia de largo plazo es **bajista** o está en transición."
            ema_status = "warning"
    else:
        ema_text = "Este instrumento no dispone de suficientes datos históricos para calcular las medias móviles exponenciales de 50 y 200 días."
        ema_status = "neutral"

    sections.append({
        "title": "Cruce de Medias Móviles (EMA 50/200)",
        "icon": "fa-chart-line",
        "content": ema_text,
        "value": trend,
        "status": ema_status
    })

    # Volatility Assessment
    vol_pct = volatility * 100
    if volatility < 0.15:
        vol_text = f"La volatilidad anualizada es de **{vol_pct:.1f}%**, considerada **baja**. Esto indica un activo predecible y estable, ideal para perfiles conservadores. El riesgo de movimientos bruscos es bajo."
        vol_status = "success"
    elif volatility < 0.30:
        vol_text = f"La volatilidad anualizada es de **{vol_pct:.1f}%**, ubicándose en un rango **moderado**. Este nivel es compatible con inversiones de mediano plazo siempre que se acompañe de un buen ratio de Sharpe."
        vol_status = "neutral"
    elif volatility < 0.50:
        vol_text = f"La volatilidad anualizada es **alta** ({vol_pct:.1f}%). Esto implica oscilaciones significativas en el precio. Adecuado para perfiles agresivos que toleran drawdowns temporales en búsqueda de rendimientos superiores."
        vol_status = "warning"
    else:
        vol_text = f"La volatilidad anualizada es **muy alta** ({vol_pct:.1f}%). Este activo presenta fluctuaciones extremas y es apto exclusivamente para inversores con alta tolerancia al riesgo y horizonte flexible."
        vol_status = "danger"

    sections.append({
        "title": "Volatilidad Anualizada",
        "icon": "fa-wave-square",
        "content": vol_text,
        "value": f"{vol_pct:.1f}%",
        "status": vol_status
    })

    # Momentum (Short-term returns)
    if ret_1m != 0:
        mom_pct = ret_1m * 100
        if ret_1m > 0.05:
            mom_text = f"El activo registró un rendimiento del **+{mom_pct:.1f}%** en el último mes, mostrando un **fuerte momentum alcista**. Los retornos de 3 meses ({ret_3m*100:.1f}%) refuerzan esta tendencia positiva."
        elif ret_1m > 0:
            mom_text = f"El rendimiento mensual es de **+{mom_pct:.1f}%**, indicando un momentum **ligeramente positivo**. El retorno trimestral ({ret_3m*100:.1f}%) ofrece una perspectiva más amplia de la dirección reciente."
        elif ret_1m > -0.05:
            mom_text = f"El rendimiento mensual es de **{mom_pct:.1f}%**, una corrección **leve** que podría representar una oportunidad de entrada si los indicadores de largo plazo son favorables."
        else:
            mom_text = f"El activo cayó un **{mom_pct:.1f}%** en el último mes, señalando un **momentum bajista** significativo. Debería confirmarse si se trata de una corrección temporal o un cambio de tendencia estructural."
    else:
        mom_text = "No se dispone de datos de rendimiento mensual para evaluar el momentum de corto plazo."

    sections.append({
        "title": "Momentum de Corto Plazo",
        "icon": "fa-bolt",
        "content": mom_text,
        "value": f"{ret_1m*100:+.1f}% (1M)",
        "status": "success" if ret_1m > 0.02 else "danger" if ret_1m < -0.03 else "neutral"
    })

    return sections





def build_fundamental_analysis(category, sharpe, ret_6m, ret_12m, tna, maturity, volatility, currency):
    sections = []

    # Sharpe Ratio
    if sharpe > 1.0:
        sh_text = f"El Ratio de Sharpe es de **{sharpe:.2f}**, lo que indica un **excelente** rendimiento ajustado por riesgo. Por cada unidad de volatilidad asumida, el inversor obtiene un retorno superior significativo por encima de la tasa libre de riesgo."
        sh_status = "success"
    elif sharpe > 0.5:
        sh_text = f"El Ratio de Sharpe es de **{sharpe:.2f}**, un valor **aceptable** que sugiere que el rendimiento compensa razonablemente el riesgo asumido. Es una relación equilibrada para horizontes de 6-12 meses."
        sh_status = "neutral"
    elif sharpe > 0:
        sh_text = f"El Ratio de Sharpe es de **{sharpe:.2f}**, un valor **bajo positivo**. El activo genera retorno por encima de la tasa libre de riesgo, pero el premio por la volatilidad asumida es marginal."
        sh_status = "warning"
    else:
        sh_text = f"El Ratio de Sharpe es **negativo** ({sharpe:.2f}), lo que significa que el retorno del activo no compensa ni siquiera la tasa libre de riesgo. Técnicamente, el inversor destruye valor ajustado por riesgo."
        sh_status = "danger"

    sections.append({
        "title": "Ratio de Sharpe (Riesgo/Retorno)",
        "icon": "fa-scale-balanced",
        "content": sh_text,
        "value": f"{sharpe:.2f}",
        "status": sh_status
    })

    # Returns Analysis
    ret_text = f"El rendimiento acumulado a 6 meses es **{ret_6m*100:+.1f}%** y a 12 meses es **{ret_12m*100:+.1f}%**. "
    if ret_6m > 0.15:
        ret_text += "Estos retornos son **superiores al promedio** del mercado y refuerzan la tesis alcista para mediano plazo."
    elif ret_6m > 0:
        ret_text += "Los retornos son **positivos pero moderados**, alineados con un contexto de crecimiento gradual."
    elif ret_6m > -0.10:
        ret_text += "La corrección reciente es **contenida**. Podría tratarse de una consolidación antes de una nueva fase alcista."
    else:
        ret_text += "La caída acumulada es **significativa** y requiere precaución. Es necesario evaluar si existen catalizadores de recuperación."

    sections.append({
        "title": "Rendimiento Acumulado (Mediano Plazo)",
        "icon": "fa-arrow-trend-up",
        "content": ret_text,
        "value": f"{ret_6m*100:+.1f}% (6M)",
        "status": "success" if ret_6m > 0.10 else "danger" if ret_6m < -0.10 else "neutral"
    })

    # Analisis vs Inflación Argentina Proyectada
    expected_ret_ars = estimate_expected_return_ars({
        "category": category,
        "currency": currency,
        "tna": tna or 0.0,
        "ret_12m": ret_12m,
        "ret_6m": ret_6m
    })
    beats_inflation = expected_ret_ars > PROJECTED_ARG_INFLATION
    spread = expected_ret_ars - PROJECTED_ARG_INFLATION
    
    if beats_inflation:
        inf_text = (
            f"El retorno anual esperado en pesos es del **{expected_ret_ars*100:.1f}%**, superando la "
            f"inflación argentina proyectada del **{PROJECTED_ARG_INFLATION*100:.1f}%** con un spread real positivo de "
            f"**+{spread*100:.1f}%**. Cumple con el objetivo del portafolio de ganarle a la inflación."
        )
        inf_status = "success"
    else:
        inf_text = (
            f"El retorno esperado en pesos es del **{expected_ret_ars*100:.1f}%**, quedando por debajo "
            f"de la inflación argentina proyectada del **{PROJECTED_ARG_INFLATION*100:.1f}%** (rendimiento real negativo de "
            f"**{spread*100:.1f}%**). No califica como sugerencia recomendada."
        )
        inf_status = "danger"

    sections.append({
        "title": "Comparativa de Inflación Argentina",
        "icon": "fa-fire-flame-curved",
        "content": inf_text,
        "value": f"Retorno Est.: {expected_ret_ars*100:.1f}%",
        "status": inf_status
    })

    # Fixed Income Specific
    if category in ("letras", "bonos") and tna is not None:
        tna_pct = tna * 100
        fi_text = f"Este instrumento de renta fija ofrece una **TNA del {tna_pct:.1f}%**"
        if maturity:
            fi_text += f" con vencimiento estimado en **{maturity}**. "
        else:
            fi_text += ". "

        if category == "letras":
            fi_text += "Las Letras del Tesoro (LECAPs) son instrumentos de **corto plazo** emitidos por el Estado Nacional. Su principal ventaja es la previsibilidad del retorno y la baja volatilidad."
        else:
            fi_text += "Los bonos soberanos soberanos argentinos en dólares/pesos incorporan **riesgo país** pero otorgan alto rendimiento potencial."

        sections.append({
            "title": "Análisis de Renta Fija",
            "icon": "fa-landmark",
            "content": fi_text,
            "value": f"TNA: {tna_pct:.1f}%",
            "status": "success" if tna > 0.22 else "neutral"
        })

    return sections


def build_macro_context(category, currency, profile):
    sections = []

    if category in ("merval", "cedears", "bonos", "letras"):
        macro_arg = (
            "**Contexto Argentina (Jul 2026):** La economía argentina transita un proceso de estabilización macroeconómica. "
            "La reducción gradual de la brecha cambiaria (dólar oficial vs. CCL) ha generado mayor previsibilidad en el mercado de capitales local. "
            "Sin embargo, la inflación acumulada sigue siendo un factor determinante para evaluar rendimientos reales en pesos. "
            "Los instrumentos en ARS deben superar la inflación esperada para generar retorno real positivo. "
            "El riesgo país sigue siendo un indicador clave para bonos soberanos."
        )
        sections.append({
            "title": "Entorno Macroeconómico Argentino",
            "icon": "fa-flag",
            "content": macro_arg,
            "status": "neutral"
        })

    if category in ("sp500", "cedears"):
        macro_us = (
            "**Contexto EE.UU. (Jul 2026):** La Reserva Federal mantiene una postura de política monetaria que equilibra el control inflacionario con el sostenimiento del empleo. "
            "Los mercados de renta variable estadounidenses han mostrado resiliencia, impulsados por el sector tecnológico y la inteligencia artificial. "
            "Los CEDEARs permiten al inversor argentino acceder a estas dinámicas con cobertura implícita en dólares (tipo de cambio CCL). "
            "El ratio P/E del S&P 500 se encuentra por encima de su promedio histórico, lo que sugiere valuaciones exigentes que podrían limitar el upside de corto plazo."
        )
        sections.append({
            "title": "Entorno de Mercados Internacionales (EE.UU.)",
            "icon": "fa-globe",
            "content": macro_us,
            "status": "neutral"
        })

    if category == "crypto":
        macro_crypto = (
            "**Contexto Criptomonedas (Jul 2026):** El mercado cripto continúa su desarrollo como clase de activo, con creciente adopción institucional. "
            "La regulación global avanza gradualmente, lo que introduce tanto oportunidades como riesgos regulatorios. "
            "Bitcoin mantiene su rol como reserva de valor digital y referencia del sector. "
            "La correlación de las criptomonedas con los mercados tradicionales varía según el ciclo: en momentos de risk-off tienden a caer junto con la renta variable, mientras que en ciclos expansivos pueden ofrecer rendimientos superiores. "
            "La alta volatilidad inherente las hace adecuadas únicamente para la porción especulativa del portafolio."
        )
        sections.append({
            "title": "Entorno del Mercado Cripto",
            "icon": "fa-bitcoin-sign",
            "content": macro_crypto,
            "status": "neutral"
        })

    return sections


def build_verdict(score, profile, category, trend, sharpe, rsi, volatility):
    if score >= 85:
        action = "COMPRAR"
        icon = "fa-circle-check"
        color = "success"
        summary = f"Este activo obtiene un score de **{score}/100** para el perfil **{profile}**, posicionándose entre las mejores alternativas disponibles. "
    elif score >= 60:
        action = "CONSIDERAR"
        icon = "fa-circle-info"
        color = "neutral"
        summary = f"Con un score de **{score}/100** para el perfil **{profile}**, este activo presenta una relación riesgo/retorno aceptable. "
    elif score >= 35:
        action = "CAUTELA"
        icon = "fa-triangle-exclamation"
        color = "warning"
        summary = f"El score de **{score}/100** indica que este activo no es ideal para el perfil **{profile}**. "
    else:
        action = "EVITAR"
        icon = "fa-circle-xmark"
        color = "danger"
        summary = f"Con un score de solo **{score}/100**, este activo no es recomendable para el perfil **{profile}**. "

    # Build reasoning
    reasons = []
    if "Alcista" in trend:
        reasons.append("La tendencia técnica es favorable y acompaña la recomendación.")
    elif "Bajista" in trend:
        reasons.append("La tendencia técnica es adversa, lo que incrementa el riesgo de pérdida en el corto plazo.")

    if sharpe > 1.0:
        reasons.append("El ratio de Sharpe indica una excelente compensación por el riesgo asumido.")
    elif sharpe < 0:
        reasons.append("El ratio de Sharpe negativo sugiere que el retorno no justifica la volatilidad.")

    if profile == "conservador" and volatility > 0.30:
        reasons.append("La volatilidad es demasiado alta para un perfil conservador orientado a la preservación de capital.")
    elif profile == "agresivo" and volatility < 0.10:
        reasons.append("La baja volatilidad limita el potencial de rendimiento para un perfil agresivo.")

    if rsi > 70:
        reasons.append("El RSI en zona de sobrecompra aconseja esperar una corrección antes de entrar.")
    elif rsi < 35:
        reasons.append("El RSI en zona de sobreventa podría representar una oportunidad contrarian si los fundamentos sostienen el precio.")

    summary += " ".join(reasons)

    return {
        "action": action,
        "icon": icon,
        "color": color,
        "summary": summary
    }
