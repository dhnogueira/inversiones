from app.scoring.profiles import (
    estimate_expected_return_ars,
    PROJECTED_ARG_INFLATION,
    get_horizon_inflation,
    HORIZON_SHORT,
    HORIZON_MEDIUM,
    HORIZON_LONG
)

import numpy as np


def build_balance_analysis(ticker, category):
    """
    Obtiene los últimos 5 balances trimestrales de un activo de renta variable
    mediante yfinance y genera un análisis narrativo con puntos favorables, críticos
    y un resumen promedio.

    Retorna None para renta fija (letras/bonos) y crypto.
    Retorna None si no hay datos disponibles.
    """
    # Solo tiene sentido para acciones
    if category in ("letras", "bonos", "crypto"):
        return None

    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)

        # Quarterly financials: ingresos y utilidad neta
        qf = stock.quarterly_financials
        # Balance sheet trimestral: deuda y equity
        qbs = stock.quarterly_balance_sheet
        # Cashflow trimestral: FCF = Operating CF - CapEx
        qcf = stock.quarterly_cashflow

        if qf is None or qf.empty:
            return None

        # Tomar las últimas 5 columnas (trimestres, más reciente primero)
        periods = list(qf.columns[:5])
        if len(periods) == 0:
            return None

        # Intentar obtener EPS trimestral
        try:
            earnings_hist = stock.quarterly_earnings
        except Exception:
            earnings_hist = None

        snapshots = []

        def safe_get_row(df, possible_keys):
            """Busca la primera clave existente en las filas del DataFrame."""
            if df is None or df.empty:
                return None
            for key in possible_keys:
                for idx in df.index:
                    if isinstance(idx, str) and key.lower() in idx.lower():
                        return df.loc[idx]
            return None

        revenue_series = safe_get_row(qf, ["Total Revenue", "Revenue"])
        net_income_series = safe_get_row(qf, ["Net Income", "Net Income Common Stockholders"])
        op_cf_series = safe_get_row(qcf, ["Operating Cash Flow", "Total Cash From Operating Activities"])
        capex_series = safe_get_row(qcf, ["Capital Expenditure", "Capital Expenditures"])
        total_debt_series = safe_get_row(qbs, ["Total Debt", "Long Term Debt"])
        equity_series = safe_get_row(qbs, ["Stockholders Equity", "Total Stockholders Equity", "Common Stock Equity"])

        revenues = []
        margins = []
        epss = []

        for col in periods:
            period_label = col.strftime("%b %Y") if hasattr(col, "strftime") else str(col)

            # Ingresos en miles de millones
            revenue = None
            if revenue_series is not None and col in revenue_series.index:
                v = revenue_series[col]
                if v is not None and not (isinstance(v, float) and np.isnan(v)):
                    revenue = round(v / 1e9, 2)

            # Utilidad neta
            net_income = None
            if net_income_series is not None and col in net_income_series.index:
                v = net_income_series[col]
                if v is not None and not (isinstance(v, float) and np.isnan(v)):
                    net_income = round(v / 1e9, 2)

            # Margen neto
            net_margin = None
            if revenue and net_income is not None and revenue != 0:
                net_margin = round((net_income / revenue) * 100, 1)

            # FCF = Operating CF - CapEx
            fcf = None
            if op_cf_series is not None and col in op_cf_series.index:
                ocf_v = op_cf_series[col]
                capex_v = 0.0
                if capex_series is not None and col in capex_series.index:
                    cv = capex_series[col]
                    if cv is not None and not (isinstance(cv, float) and np.isnan(cv)):
                        capex_v = cv
                if ocf_v is not None and not (isinstance(ocf_v, float) and np.isnan(ocf_v)):
                    fcf = round((ocf_v - abs(capex_v)) / 1e9, 2)

            # Deuda / Equity
            debt_equity = None
            if (total_debt_series is not None and col in total_debt_series.index and
                    equity_series is not None and col in equity_series.index):
                dv = total_debt_series[col]
                ev = equity_series[col]
                if (dv is not None and ev is not None and
                        not (isinstance(dv, float) and np.isnan(dv)) and
                        not (isinstance(ev, float) and np.isnan(ev)) and ev != 0):
                    debt_equity = round(dv / ev, 2)

            # EPS de la historia de earnings si está disponible
            eps = None
            if earnings_hist is not None and not earnings_hist.empty:
                if hasattr(col, "quarter") and hasattr(col, "year"):
                    # Buscar por año/trimestre aproximado
                    for eidx in earnings_hist.index:
                        try:
                            if hasattr(eidx, "year") and eidx.year == col.year and eidx.quarter == col.quarter:
                                row_e = earnings_hist.loc[eidx]
                                if "EPS Actual" in row_e.index:
                                    eps = round(float(row_e["EPS Actual"]), 2)
                                elif "Earnings" in row_e.index:
                                    eps = round(float(row_e["Earnings"]), 2)
                        except Exception:
                            pass

            # Generar puntos favorables y críticos
            favorable = []
            critical = []

            if net_margin is not None:
                if net_margin >= 20:
                    favorable.append(f"Margen neto sólido del {net_margin}%")
                elif net_margin >= 10:
                    pass  # neutral
                elif net_margin < 5:
                    critical.append(f"Margen neto muy bajo: {net_margin}%")
                elif net_margin < 0:
                    critical.append(f"Margen neto negativo: {net_margin}%")

            if fcf is not None:
                if fcf > 0:
                    favorable.append(f"FCF positivo: ${fcf:.1f}B")
                else:
                    critical.append(f"FCF negativo: ${fcf:.1f}B (quema de caja)")

            if debt_equity is not None:
                if debt_equity < 0.5:
                    favorable.append(f"Deuda/Equity baja: {debt_equity:.2f}")
                elif debt_equity > 2:
                    critical.append(f"Deuda/Equity elevada: {debt_equity:.2f}")

            if revenue is not None and revenue > 0:
                if len(revenues) > 0 and revenues[-1] is not None:
                    chg = ((revenue - revenues[-1]) / revenues[-1]) * 100
                    if chg >= 5:
                        favorable.append(f"Ingresos en alza vs trimestre anterior: +{chg:.1f}%")
                    elif chg <= -5:
                        critical.append(f"Ingresos en baja vs trimestre anterior: {chg:.1f}%")

            revenues.append(revenue)
            if net_margin is not None:
                margins.append(net_margin)
            if eps is not None:
                epss.append(eps)

            snapshots.append({
                "period": period_label,
                "revenue_b": revenue,
                "net_income_b": net_income,
                "net_margin_pct": net_margin,
                "eps": eps,
                "fcf_b": fcf,
                "debt_equity": debt_equity,
                "favorable": favorable,
                "critical": critical
            })

        if not snapshots:
            return None

        # --- Resumen promedio de los 5 balances ---
        valid_revenues = [r for r in revenues if r is not None]
        valid_margins = [m for m in margins if m is not None]
        valid_epss = [e for e in epss if e is not None]

        avg_revenue = round(sum(valid_revenues) / len(valid_revenues), 2) if valid_revenues else None
        avg_margin = round(sum(valid_margins) / len(valid_margins), 1) if valid_margins else None
        avg_eps = round(sum(valid_epss) / len(valid_epss), 2) if valid_epss else None

        # Tendencia de ingresos (entre el primero y el último válido)
        revenue_trend = "sin datos"
        if len(valid_revenues) >= 2:
            # Recordar: la lista está ordenada de más reciente a más antiguo
            delta = valid_revenues[0] - valid_revenues[-1]
            if delta > 0:
                revenue_trend = "creciente"
            elif delta < 0:
                revenue_trend = "decreciente"
            else:
                revenue_trend = "estable"

        margin_trend = "sin datos"
        if len(valid_margins) >= 2:
            delta_m = valid_margins[0] - valid_margins[-1]
            if delta_m > 1:
                margin_trend = "en expansión"
            elif delta_m < -1:
                margin_trend = "en contracción"
            else:
                margin_trend = "estable"

        # Conclusión basada en margen, FCF y tendencia
        all_favorable = sum(len(s["favorable"]) for s in snapshots)
        all_critical = sum(len(s["critical"]) for s in snapshots)

        if avg_margin is not None and avg_margin >= 15 and revenue_trend == "creciente" and all_critical == 0:
            conclusion = "SÓLIDO"
            conclusion_color = "success"
            conclusion_detail = (
                f"Los últimos {len(snapshots)} balances muestran una empresa con ingresos {revenue_trend}s, "
                f"márgenes de {avg_margin:.1f}% promedio y sin señales de alerta. "
                f"Los fundamentos respaldan la tesis de inversión."
            )
        elif avg_margin is not None and avg_margin >= 5 and all_critical <= all_favorable:
            conclusion = "ESTABLE"
            conclusion_color = "neutral"
            conclusion_detail = (
                f"Los últimos {len(snapshots)} balances presentan estabilidad general con ingresos {revenue_trend}s "
                f"y margen promedio del {avg_margin:.1f}%. "
                f"Hay {all_critical} señales de atención y {all_favorable} puntos positivos. Perfil de riesgo moderado."
            )
        else:
            conclusion = "CON SEÑALES DE ALERTA"
            conclusion_color = "warning"
            conclusion_detail = (
                f"Los últimos {len(snapshots)} balances detectan {all_critical} señales críticas frente a {all_favorable} favorables. "
                f"Se observan presiones en la rentabilidad "
                + (f"(margen {avg_margin:.1f}%, {margin_trend})" if avg_margin is not None else "")
                + f" con ingresos {revenue_trend}s. Se recomienda precaución."
            )

        balance_summary = {
            "periods_analyzed": len(snapshots),
            "avg_revenue_b": avg_revenue,
            "avg_net_margin_pct": avg_margin,
            "avg_eps": avg_eps,
            "revenue_trend": revenue_trend,
            "margin_trend": margin_trend,
            "total_favorable_signals": all_favorable,
            "total_critical_signals": all_critical,
            "conclusion": conclusion,
            "conclusion_color": conclusion_color,
            "conclusion_detail": conclusion_detail
        }

        return {
            "snapshots": snapshots,
            "summary": balance_summary
        }

    except Exception as e:
        # Si yfinance falla (activo sin datos, timeout, etc.) retornar None silenciosamente
        print(f"[balance_analysis] No se pudieron obtener balances para {ticker}: {e}")
        return None

def calculate_tp_sl(price, volatility, profile, category, horizon="medium"):
    """
    Calcula dinámicamente el Take Profit y Stop Loss sugeridos
    según la volatilidad del activo, el perfil de riesgo seleccionado y el horizonte temporal.
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
            
    # Ajuste por horizonte de inversión
    if horizon == "short":
        # Corto plazo (hasta 6 meses): asegurar ganancias rápido con TP/SL más ajustados
        tp_pct *= 0.60
        sl_pct *= 0.60
    elif horizon == "long":
        # Largo plazo (>1 año): dar más margen para absorber oscilaciones normales
        tp_pct *= 1.80
        sl_pct *= 1.60

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


def generate_asset_analysis(asset, profile, horizon="medium"):
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
    fundamental = build_fundamental_analysis(category, sharpe, ret_6m, ret_12m, tna, maturity, volatility, currency, profile, horizon)

    # ------- Sección 3: Contexto Macroeconómico -------
    macro = build_macro_context(category, currency, profile)

    # ------- Sección 4: Veredicto Final -------
    tp, sl, tp_pct, sl_pct = calculate_tp_sl(price, volatility, profile, category, horizon)
    verdict = build_verdict(score, profile, category, trend, sharpe, rsi, volatility)
    verdict["take_profit"] = tp
    verdict["stop_loss"] = sl
    verdict["tp_pct"] = tp_pct
    verdict["sl_pct"] = sl_pct

    # ------- Sección 5: Análisis de Balances (últimos 5 trimestres) -------
    balances = build_balance_analysis(ticker, category)

    return {
        "ticker": ticker,
        "name": name,
        "category": category,
        "price": price,
        "currency": currency,
        "score": score,
        "profile": profile,
        "horizon": horizon,
        "technical": technical,
        "fundamental": fundamental,
        "macro": macro,
        "balances": balances,
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





def build_fundamental_analysis(category, sharpe, ret_6m, ret_12m, tna, maturity, volatility, currency, profile="moderado", horizon="medium"):
    sections = []

    # Sharpe Ratio
    sharpe_intro = (
        f"**¿Qué mide?** El Ratio de Sharpe responde a la pregunta: "
        f"_¿cuánto rendimiento extra obtengo por cada unidad de riesgo que asumo?_ "
        f"Compara el retorno del activo contra la **tasa libre de riesgo** (lo que ganarías sin arriesgar nada). "
        f"Un valor positivo indica que el activo rinde más de lo mínimo esperado; un valor negativo "
        f"indica que **no conviene asumir ese riesgo**, porque rendirías menos que dejando el dinero en un instrumento seguro."
    )
    if sharpe > 1.0:
        sh_detail = (
            f"El Ratio de Sharpe de este activo es **{sharpe:.2f}** (excelente, > 1.0): por cada punto de volatilidad "
            f"asumida, el activo genera un retorno significativamente superior a la tasa libre de riesgo. "
            f"Esto lo posiciona como una inversión **muy eficiente** en relación al riesgo tomado."
        )
        sh_status = "success"
    elif sharpe > 0.5:
        sh_detail = (
            f"El Ratio de Sharpe de este activo es **{sharpe:.2f}** (aceptable, entre 0.5 y 1.0): el rendimiento "
            f"compensa razonablemente el riesgo asumido. Es una relación **equilibrada** para horizontes de 6-12 meses."
        )
        sh_status = "neutral"
    elif sharpe > 0:
        sh_detail = (
            f"El Ratio de Sharpe de este activo es **{sharpe:.2f}** (bajo positivo, entre 0 y 0.5): el activo genera "
            f"retorno por encima de la tasa libre de riesgo, pero el **premio por volatilidad es marginal**. "
            f"Hay alternativas más eficientes disponibles."
        )
        sh_status = "warning"
    else:
        sh_detail = (
            f"El Ratio de Sharpe de este activo es **{sharpe:.2f}** (negativo): el retorno del activo **no alcanza "
            f"ni la tasa libre de riesgo**. En términos prácticos, el inversor destruye valor ajustado por riesgo: "
            f"asumir esta volatilidad no está siendo recompensado."
        )
        sh_status = "danger"

    sh_text = sharpe_intro + "\n\n" + sh_detail

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

    # Analisis vs Inflación Argentina Proyectada (ajustado al perfil de riesgo y horizonte)
    expected_ret_ars = estimate_expected_return_ars({
        "category": category,
        "currency": currency,
        "tna": tna or 0.0,
        "ret_12m": ret_12m,
        "ret_6m": ret_6m,
        "maturity": maturity
    }, profile, horizon)
    
    horizon_inflation = get_horizon_inflation(horizon)
    beats_inflation = expected_ret_ars > horizon_inflation
    spread = expected_ret_ars - horizon_inflation
    
    horizon_names = {
        HORIZON_SHORT: "corto plazo (hasta 6 meses)",
        HORIZON_MEDIUM: "mediano plazo (6 a 12 meses)",
        HORIZON_LONG: "largo plazo (más de 1 año)"
    }
    h_name = horizon_names.get(horizon, "mediano plazo")
    
    if beats_inflation:
        inf_text = (
            f"El retorno estimado en pesos para este activo en un horizonte de **{h_name}** es del **{expected_ret_ars*100:.1f}%**, "
            f"superando la inflación proyectada del período del **{horizon_inflation*100:.1f}%** con un spread real positivo de "
            f"**+{spread*100:.1f}%**. Cumple con el objetivo de preservar y acrecentar el poder adquisitivo."
        )
        inf_status = "success"
    else:
        inf_text = (
            f"El retorno estimado en pesos para este activo en un horizonte de **{h_name}** es del **{expected_ret_ars*100:.1f}%**, "
            f"quedando por debajo de la inflación proyectada del período de **{horizon_inflation*100:.1f}%** (rendimiento real negativo de "
            f"**{spread*100:.1f}%**). Por lo tanto, no califica como una recomendación robusta para esta ventana temporal."
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
