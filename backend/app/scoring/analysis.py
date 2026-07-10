from app.scoring.profiles import (
    estimate_expected_return_ars,
    PROJECTED_ARG_INFLATION,
    get_horizon_inflation,
    HORIZON_SHORT,
    HORIZON_MEDIUM,
    HORIZON_LONG
)

import numpy as np

# Cache in-process to optimize local build compile time and bypass yfinance rate limits
_balance_cache = {}

def load_existing_balance_from_static(ticker):
    """
    Busca si ya existe un archivo JSON compilado para el mismo ticker
    que contenga datos de 'balances' válidos en alguna de las subcarpetas del frontend.
    """
    import os
    import glob
    import json
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        pattern = os.path.join(base_dir, "frontend", "api", "asset-analysis", "*", f"{ticker}.json")
        for path in glob.glob(pattern):
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("status") == "success" and data.get("analysis") and data["analysis"].get("balances"):
                    return data["analysis"]["balances"]
    except Exception as e:
        print(f"[load_existing_balance_from_static] Error para {ticker}: {e}")
    return None

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

    # Check cache
    cache_key = (ticker, category)
    if cache_key in _balance_cache:
        return _balance_cache[cache_key]

    result = None
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
            raise ValueError("Quarterly financials is empty")

        # Tomar las últimas 5 columnas (trimestres, más reciente primero)
        periods = list(qf.columns[:5])
        if len(periods) == 0:
            raise ValueError("No quarters available in quarterly financials")

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
            raise ValueError("No snapshots compiled")

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

        result = {
            "snapshots": snapshots,
            "summary": balance_summary
        }
    except Exception as e:
        print(f"[balance_analysis] yfinance falló para {ticker}: {e}. Intentando fallback local...")
        result = load_existing_balance_from_static(ticker)

    _balance_cache[cache_key] = result
    return result


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
    high_52w = asset.get("high_52w", None)
    drawdown_pct = asset.get("drawdown_pct", None)
    fundamental = build_fundamental_analysis(category, sharpe, ret_6m, ret_12m, tna, maturity, volatility, currency, profile, horizon, high_52w, drawdown_pct)

    # ------- Sección 3: Contexto Macroeconómico -------
    macro = build_macro_context(category, currency, profile)

    # ------- Sección 4: Veredicto Final -------
    tp, sl, tp_pct, sl_pct = calculate_tp_sl(price, volatility, profile, category, horizon)
    verdict = build_verdict(score, profile, category, trend, sharpe, rsi, volatility, tna)
    verdict["take_profit"] = tp
    verdict["stop_loss"] = sl
    verdict["tp_pct"] = tp_pct
    verdict["sl_pct"] = sl_pct

    # ------- Sección 5: Análisis de Balances (+ltimos 5 trimestres) -------
    balances = build_balance_analysis(ticker, category)

    # ------- Sección 6-8: Estrategias de Largo Plazo (solo cuando horizon=long) -------
    long_term_strategies = None
    if horizon == HORIZON_LONG and category not in ("letras", "bonos", "crypto"):
        long_term_strategies = {
            "value": build_value_investing_analysis(asset, currency),
            "quality": build_quality_investing_analysis(asset, currency),
            "dividend": build_dividend_growth_analysis(asset, currency),
        }

    # ------- Sección 9-12: Estrategias de Mediano Plazo (solo cuando horizon=medium) -------
    medium_term_strategies = None
    if horizon == HORIZON_MEDIUM and category not in ("letras", "bonos"):
        medium_term_strategies = {
            "earnings_revision": build_earnings_revision_analysis(asset, currency),
            "can_slim": build_can_slim_analysis(asset, currency),
            "relative_strength": build_relative_strength_analysis(asset, currency),
            "garp": build_garp_analysis(asset, currency),
        }

    result = {
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
    if long_term_strategies:
        result["long_term_strategies"] = long_term_strategies
    if medium_term_strategies:
        result["medium_term_strategies"] = medium_term_strategies
    return result



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





def build_fundamental_analysis(category, sharpe, ret_6m, ret_12m, tna, maturity, volatility, currency, profile="moderado", horizon="medium", high_52w=None, drawdown_pct=None):
    sections = []

    # Drawdown-from-Peak Value Accumulation Analysis (Largo Plazo)
    if horizon == "long" and category not in ("letras", "bonos") and drawdown_pct is not None and high_52w is not None:
        dd_val = drawdown_pct * 100
        
        if category == "crypto":
            is_acc = 20.0 <= dd_val <= 65.0
        else: # equities (sp500, cedears, merval)
            is_acc = 12.0 <= dd_val <= 40.0
            
        is_peak = dd_val < 2.0  # menos de 2% de caída desde el máximo es considerado pico
        
        title = "Zona de Acumulación (Drawdown)"
        icon = "fa-layer-group"
        value = f"-{dd_val:.1f}%"
        
        if is_acc:
            content = (
                f"**¿Qué significa?** Este activo cotiza un **{dd_val:.1f}%** por debajo "
                f"de su máximo anual de **{currency} {high_52w:,.2f}**. "
                f"Para horizontes de largo plazo, este descuento representa una **Zona de Acumulación Óptima**. "
                f"La relación riesgo/retorno es altamente asimétrica a favor del inversor, permitiendo comprar activos a precios de descuento."
            )
            status = "success"
        elif is_peak:
            content = (
                f"**¿Qué significa?** El activo cotiza cerca de su máximo anual de **{currency} {high_52w:,.2f}** "
                f"(descuento mínimo del **{dd_val:.1f}%**), lo que indica una zona de **máximos (Peak-FOMO)**. "
                f"Para un inversor de largo plazo, comprar en esta zona representa un riesgo de entrar en la parte alta del mercado. "
                f"Se recomienda cautela o compras escalonadas (DCA) para mitigar el riesgo de reversión rápida."
            )
            status = "warning"
        else:
            content = (
                f"**¿Qué significa?** El activo presenta un descuento del **{dd_val:.1f}%** respecto a su máximo anual de "
                f"**{currency} {high_52w:,.2f}**. Se encuentra en una **Zona Neutral** de precio para el largo plazo, "
                f"por lo que su conveniencia depende de los fundamentos generales."
            )
            status = "neutral"
            
        sections.append({
            "title": title,
            "icon": icon,
            "content": content,
            "value": value,
            "status": status
        })

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


def build_verdict(score, profile, category, trend, sharpe, rsi, volatility, tna=None):
    tna_val = (tna * 100) if tna is not None else 0.0

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

    # Generar explicación detallada y concreta según la nota del scoring
    if category in ("letras", "bonos"):
        if score >= 85:
            why = (
                f"**Por qué esta estrategia:** El instrumento de renta fija ofrece un rendimiento esperado que supera cómodamente "
                f"la tasa de inflación proyectada para el horizonte seleccionado, con un vencimiento y TNA ({tna_val:.1f}%) que se "
                f"ajustam óptimamente a los límites de riesgo del perfil **{profile}**."
            )
        elif score >= 60:
            why = (
                f"**Por qué esta estrategia:** El activo es viable y ofrece un rendimiento aceptable de {tna_val:.1f}%, pero el score se modera "
                f"debido a un spread más estrecho sobre la inflación o un leve descalce de plazos respecto al horizonte del perfil."
            )
        else:
            why = (
                f"**Por qué esta estrategia:** Se indica cautela/evitación debido a que el rendimiento esperado real (ajustado por devaluación "
                f"e inflación del período) es negativo, o bien porque el vencimiento excede el límite del perfil **{profile}**, exponiendo al inversor "
                f"a un riesgo de tasa o liquidez no deseado."
            )
    else: # Renta variable / Crypto
        if score >= 85:
            why = (
                f"**Por qué esta estrategia:** Este activo reúne una combinación técnica y fundamental sobresaliente. "
                f"La tendencia alcista está consolidada ({trend}), el momentum es fuerte, y la eficiencia riesgo/retorno (Sharpe: {sharpe:.2f}) "
                f"es óptima para el perfil **{profile}**, ofreciendo un sólido margen de seguridad en relación a su volatilidad ({volatility*100:.1f}%)."
            )
        elif score >= 60:
            why = (
                f"**Por qué esta estrategia:** El activo presenta buenos fundamentos pero con un timing técnico o volatilidad intermedia. "
                f"Se recomienda en ponderaciones moderadas ya que, aunque la tendencia es aceptable, el ratio Sharpe ({sharpe:.2f}) "
                f"o las oscilaciones de corto plazo restan convicción para una asignación agresiva en el perfil **{profile}**."
            )
        elif score >= 35:
            why = (
                f"**Por qué esta estrategia:** Existen desalineaciones claras entre las características del activo y el perfil **{profile}**. "
                f"Esto puede deberse a una volatilidad excesiva ({volatility*100:.1f}%), un ratio de Sharpe ineficiente ({sharpe:.2f}), "
                f"o una tendencia técnica desfavorable ({trend}) que aumenta el riesgo de entrada en este momento."
            )
        else:
            why = (
                f"**Por qué esta estrategia:** El activo es descartado debido a que no cumple con los requisitos mínimos de idoneidad "
                f"para el perfil **{profile}**. Presenta un retorno histórico/esperado deficiente frente a la devaluación/inflación proyectada, "
                f"una volatilidad desmedida, o una tendencia bajista pronunciada ({trend})."
            )

    return {
        "action": action,
        "icon": icon,
        "color": color,
        "summary": summary,
        "why": why
    }


# ============================================================
#   ESTRATEGIAS DE LARGO PLAZO
# ============================================================

def build_value_investing_analysis(asset, currency):
    """
    Value Investing (Graham / Buffett).
    Evalúa PER, P/B, FCF yield, ROE, márgenes y deuda.
    """
    sections = []

    pe = asset.get("pe_ratio")
    pb = asset.get("pb_ratio")
    fcf_yield = asset.get("fcf_yield")
    roe = asset.get("roe")
    profit_margin = asset.get("profit_margin")
    debt_to_equity = asset.get("debt_to_equity")

    # --- PER (Price / Earnings) ---
    if pe is not None:
        if pe < 15:
            pe_text = f"El **PER de {pe:.1f}x** es bajo (< 15x), indicando que el mercado valúa la empresa a un precio razonable o incluso barato respecto a sus ganancias. Benjamin Graham consideraba este rango como zona de valor."
            pe_status = "success"
        elif pe < 25:
            pe_text = f"El **PER de {pe:.1f}x** se encuentra en un rango moderado (15-25x). No es barato ni caro según el criterio clásico de Graham; el precio ya descuenta cierto crecimiento futuro."
            pe_status = "neutral"
        else:
            pe_text = f"El **PER de {pe:.1f}x** es elevado (> 25x). El mercado paga una prima alta por esta acción respecto a sus ganancias actuales. Requiere un crecimiento sostenido para justificar la valuación."
            pe_status = "warning"
    else:
        pe_text = "No hay datos de PER disponibles para este activo (puede ser una empresa sin ganancias positivas o un CEDEAR sin cobertura directa)."
        pe_status = "neutral"

    sections.append({
        "title": "PER — Price / Earnings",
        "icon": "fa-tag",
        "content": pe_text,
        "value": f"{pe:.1f}x" if pe else "N/D",
        "status": pe_status
    })

    # --- P/B (Precio / Valor Libros) ---
    if pb is not None:
        if pb < 1.5:
            pb_text = f"El **P/B de {pb:.2f}x** es bajo. La empresa cotiza cerca o por debajo de su valor en libros, lo que históricamente (Graham) representa una oportunidad de margen de seguridad elevado."
            pb_status = "success"
        elif pb < 3.0:
            pb_text = f"El **P/B de {pb:.2f}x** es razonable. El mercado paga una moderada prima sobre el valor contable, coherente con empresas de calidad que generan retorbos superiores al promedio."
            pb_status = "neutral"
        else:
            pb_text = f"El **P/B de {pb:.2f}x** es alto. La empresa cotiza a una prima significativa sobre su valor en libros. Esto puede justificarse por una ventaja competitiva (moat) sólida, pero ofrece menos margen de seguridad."
            pb_status = "warning"
    else:
        pb_text = "El Precio/Valor Libro no está disponible para este activo."
        pb_status = "neutral"

    sections.append({
        "title": "Precio / Valor Libro (P/B)",
        "icon": "fa-book-open",
        "content": pb_text,
        "value": f"{pb:.2f}x" if pb else "N/D",
        "status": pb_status
    })

    # --- FCF Yield ---
    if fcf_yield is not None:
        fcf_pct = fcf_yield * 100
        if fcf_yield > 0.04:
            fcf_text = f"El **FCF Yield del {fcf_pct:.1f}%** es robusto. La empresa genera abundante flujo de caja libre en relación a su capitalización bursátil, lo que le permite reinvertir, pagar dividendos y recomprar acciones sin depender de deuda."
            fcf_status = "success"
        elif fcf_yield > 0:
            fcf_text = f"El **FCF Yield del {fcf_pct:.1f}%** es positivo pero moderado. La empresa genera caja libre, aunque el margen no es especialmente generoso a este nivel de precio."
            fcf_status = "neutral"
        else:
            fcf_text = f"El **FCF Yield es negativo ({fcf_pct:.1f}%)**. La empresa está en etapa de inversión intensa (quema de caja). Puede ser estratégico, pero requiere vigilar que la reinversión genere retornos futuros superiores al costo del capital."
            fcf_status = "danger"
    else:
        fcf_text = "No se dispone de datos de flujo de caja libre para este activo."
        fcf_status = "neutral"

    sections.append({
        "title": "Flujo de Caja Libre (FCF Yield)",
        "icon": "fa-money-bill-wave",
        "content": fcf_text,
        "value": f"{fcf_yield*100:.1f}%" if fcf_yield is not None else "N/D",
        "status": fcf_status
    })

    # --- ROE ---
    if roe is not None:
        roe_pct = roe * 100
        if roe > 0.15:
            roe_text = f"El **ROE del {roe_pct:.1f}%** es excelente (> 15%). La empresa genera una alta rentabilidad sobre el capital de los accionistas, señal de ventaja competitiva sostenible. Buffett considera el ROE alto consistente como uno de los indicadores más confiables de una gran empresa."
            roe_status = "success"
        elif roe > 0.08:
            roe_text = f"El **ROE del {roe_pct:.1f}%** es aceptable (8-15%). La gestión del capital es razonable sin ser excepcional."
            roe_status = "neutral"
        else:
            roe_text = f"El **ROE del {roe_pct:.1f}%** es bajo (< 8%). La empresa no genera una rentabilidad suficiente sobre el capital invertido, lo que reduce el atractivo como inversión de valor a largo plazo."
            roe_status = "warning"
    else:
        roe_text = "No hay datos de ROE disponibles para este activo."
        roe_status = "neutral"

    sections.append({
        "title": "ROE — Rentabilidad sobre Patrimonio",
        "icon": "fa-percent",
        "content": roe_text,
        "value": f"{roe*100:.1f}%" if roe is not None else "N/D",
        "status": roe_status
    })

    # --- Deuda (D/E) ---
    if debt_to_equity is not None:
        if debt_to_equity < 0.5:
            de_text = f"La relación **Deuda/Patrimonio de {debt_to_equity:.2f}x** es baja. La empresa opera con financiamiento propio predominante, lo que le otorga solidez y flexibilidad financiera ante ciclos adversos."
            de_status = "success"
        elif debt_to_equity < 1.5:
            de_text = f"La relación **Deuda/Patrimonio de {debt_to_equity:.2f}x** es moderada y manejable, habitual en empresas maduras que usan apalancamiento de forma controlada."
            de_status = "neutral"
        else:
            de_text = f"La relación **Deuda/Patrimonio de {debt_to_equity:.2f}x** es alta. Un apalancamiento elevado amplifica los riesgos en períodos de suba de tasas o menores ingresos."
            de_status = "warning"
    else:
        de_text = "Datos de deuda no disponibles para este activo."
        de_status = "neutral"

    sections.append({
        "title": "Bajo Endeudamiento (D/E)",
        "icon": "fa-shield-halved",
        "content": de_text,
        "value": f"{debt_to_equity:.2f}x" if debt_to_equity is not None else "N/D",
        "status": de_status
    })

    return sections


def build_quality_investing_analysis(asset, currency):
    """
    Quality Investing: Value + Quality + Momentum + Low Volatility.
    Combina márgenes operativos, Sharpe, retornos y volatilidad baja.
    """
    sections = []

    profit_margin = asset.get("profit_margin")
    operating_margin = asset.get("operating_margin")
    roe = asset.get("roe")
    sharpe = asset.get("sharpe", 0.0) or 0.0
    volatility = asset.get("volatility", 0.3) or 0.3
    ret_12m = asset.get("ret_12m", 0.0) or 0.0
    ret_3m = asset.get("ret_3m", 0.0) or 0.0
    pe = asset.get("pe_ratio")

    # --- Margen Operativo (Quality of earnings) ---
    if operating_margin is not None:
        op_pct = operating_margin * 100
        if operating_margin > 0.20:
            om_text = f"El **margen operativo del {op_pct:.1f}%** es elevado. Empresas con márgenes operativos superiores al 20% reflejan ventajas competitivas estructurales ('moat'): poder de fijación de precios, economías de escala o diferenciación de producto. Factor clave en Quality Investing."
            om_status = "success"
        elif operating_margin > 0.10:
            om_text = f"El **margen operativo del {op_pct:.1f}%** es bueno (10-20%), coherente con empresas del sector que operan eficientemente."
            om_status = "neutral"
        elif operating_margin > 0:
            om_text = f"El **margen operativo del {op_pct:.1f}%** es bajo pero positivo. La empresa es rentable a nivel operativo, aunque con poca holgura ante presiones de costos."
            om_status = "warning"
        else:
            om_text = f"El **margen operativo es negativo ({op_pct:.1f}%)**. La empresa consume más recursos de los que genera a nivel operativo, lo cual es una señal de alerta importante para una inversión de calidad a largo plazo."
            om_status = "danger"
    else:
        om_text = "No se dispone de datos de margen operativo. Este indicador es fundamental para evaluar la calidad del negocio."
        om_status = "neutral"

    sections.append({
        "title": "Márgenes Consistentes (Quality)",
        "icon": "fa-chart-pie",
        "content": om_text,
        "value": f"{operating_margin*100:.1f}%" if operating_margin is not None else "N/D",
        "status": om_status
    })

    # --- Momentum de 3 meses ---
    mom_pct = ret_3m * 100
    if ret_3m > 0.10:
        mom_text = f"El **momentum de 3 meses (+{mom_pct:.1f}%)** es fuerte. Los mercados muestran persistencia de rendimiento: activos que superan al mercado en los últimos 3-12 meses tienden a seguir haciéndolo. Esta es la base del factor Momentum en Quality Investing."
        mom_status = "success"
    elif ret_3m > 0:
        mom_text = f"El **momentum trimestral (+{mom_pct:.1f}%)** es levemente positivo. El activo supera a la tasa libre de riesgo en el corto plazo aunque sin una aceleración marcada."
        mom_status = "neutral"
    else:
        mom_text = f"El **momentum trimestral ({mom_pct:.1f}%)** es negativo. Desde la perspectiva del factor Momentum, este activo no está mostrando la dinámica de precio favorable que caracteriza las inversiones de quality en fase alcista."
        mom_status = "warning"

    sections.append({
        "title": "Momentum (Factor de Precio)",
        "icon": "fa-rocket",
        "content": mom_text,
        "value": f"{ret_3m*100:+.1f}% (3M)",
        "status": mom_status
    })

    # --- Low Volatility Factor ---
    vol_pct = volatility * 100
    if volatility < 0.20:
        lv_text = f"La **volatilidad anualizada del {vol_pct:.1f}%** es baja. Uno de los hallazgos más contraintuitivos de las finanzas modernas es que activos de baja volatilidad superan en retorno ajustado por riesgo a los de alta volatilidad en el largo plazo (Low Volatility Anomaly). Este activo encaja en ese perfil."
        lv_status = "success"
    elif volatility < 0.35:
        lv_text = f"La **volatilidad anualizada del {vol_pct:.1f}%** es moderada. El activo no representa riesgo extremo y puede utilizarse como pilar estabilizador en un portafolio diversificado."
        lv_status = "neutral"
    else:
        lv_text = f"La **volatilidad anualizada del {vol_pct:.1f}%** es alta. El factor Low Volatility indica cautela: a largo plazo, los activos muy volátiles suelen ofrecer peor relación riesgo/retorno que los más estables."
        lv_status = "warning"

    sections.append({
        "title": "Baja Volatilidad (Low Vol Factor)",
        "icon": "fa-water",
        "content": lv_text,
        "value": f"{vol_pct:.1f}%",
        "status": lv_status
    })

    # --- Small / Large Cap context via P/E proxy ---
    if pe is not None:
        sc_text = (
            f"**Contexto PER vs. Factor Value/Quality:** El PER de {pe:.1f}x posiciona a esta empresa en el segmento de "
            + ("valuación razonable, donde convergen los factores Value y Quality a largo plazo." if pe < 20 else
               "crecimiento premium, más cercano al Quality puro que al Value estricto.")
        )
    else:
        sc_text = "No hay datos de PER para contextualizar el factor Small Cap / Valuación relativa."

    sections.append({
        "title": "Factor Value / Quality (Contexto PER)",
        "icon": "fa-building-columns",
        "content": sc_text,
        "value": f"{pe:.1f}x" if pe else "N/D",
        "status": "neutral"
    })

    return sections


def build_dividend_growth_analysis(asset, currency):
    """
    Dividend Growth Investing.
    No busca el dividendo más alto, sino el que crece sostenidamente año a año.
    """
    sections = []

    dividend_yield = asset.get("dividend_yield")
    payout_ratio = asset.get("payout_ratio")
    dividend_growing = asset.get("dividend_growing", False)
    roe = asset.get("roe")
    profit_margin = asset.get("profit_margin")
    debt_to_equity = asset.get("debt_to_equity")

    # --- Dividend Yield ---
    if dividend_yield is not None and dividend_yield > 0:
        dy_pct = dividend_yield * 100
        if 1.5 <= dy_pct <= 5.0:
            dy_text = (
                f"El **dividend yield del {dy_pct:.2f}%** se encuentra en el rango óptimo para Dividend Growth Investing (1.5% - 5%). "
                f"No se busca el mayor dividendo del mercado, sino uno **sostenible y creciente**: Coca-Cola, Johnson & Johnson y Procter & Gamble operan en este rango. "
                f"Un yield extremadamente alto (> 6-7%) muchas veces señala que el mercado descuenta un recorte del dividendo."
            )
            dy_status = "success"
        elif dy_pct < 1.5:
            dy_text = f"El **dividend yield del {dy_pct:.2f}%** es bajo. La empresa puede ser de alta calidad y con crecimiento de dividendos, pero actualmente paga poco en términos absolutos. Podría corresponder a una empresa de crecimiento que reinvierte en lugar de distribuir."
            dy_status = "neutral"
        else:
            dy_text = f"El **dividend yield del {dy_pct:.2f}%** es muy alto (> 5%). Históricamente, yields superiores al 5-6% suelen señalar que el mercado descuenta riesgos de sostenibilidad del dividendo. Analizar el payout ratio es crítico en este caso."
            dy_status = "warning"
    else:
        dy_text = "Este activo **no paga dividendos** actualmente. No encaja en el perfil de Dividend Growth Investing clásico. Para inversores de renta pasiva, este activo debería complementarse con otros de la cartera que sí generen flujo de dividendos."
        dy_status = "neutral"

    sections.append({
        "title": "Dividend Yield (Rendimiento por Dividendo)",
        "icon": "fa-coins",
        "content": dy_text,
        "value": f"{dividend_yield*100:.2f}%" if dividend_yield else "Sin dividendo",
        "status": dy_status
    })

    # --- Payout Ratio ---
    if payout_ratio is not None and payout_ratio > 0:
        pr_pct = payout_ratio * 100
        if payout_ratio < 0.60:
            pr_text = f"El **payout ratio del {pr_pct:.0f}%** es saludable. La empresa distribuye menos del 60% de sus ganancias, reteniendo capital suficiente para continuar creciendo y **aumentar el dividendo en el futuro**. Este es el indicador más importante del Dividend Growth Investing: la capacidad de subir el dividendo año a año."
            pr_status = "success"
        elif payout_ratio < 0.85:
            pr_text = f"El **payout ratio del {pr_pct:.0f}%** es moderado-alto. La empresa distribuye una parte significativa de sus ganancias. El crecimiento futuro del dividendo dependerá de que la empresa continúe expandiendo sus beneficios."
            pr_status = "neutral"
        else:
            pr_text = f"El **payout ratio del {pr_pct:.0f}%** es muy alto. La empresa distribuye casi la totalidad de sus ganancias, lo que deja poco margen para incrementar el dividendo o absorber una caída en los ingresos. Señal de alerta para el crecimiento sostenido del dividendo."
            pr_status = "warning"
    else:
        pr_text = "No hay datos de payout ratio disponibles para este activo."
        pr_status = "neutral"

    sections.append({
        "title": "Payout Ratio (Sostenibilidad del Dividendo)",
        "icon": "fa-sliders",
        "content": pr_text,
        "value": f"{payout_ratio*100:.0f}%" if payout_ratio else "N/D",
        "status": pr_status
    })

    # --- Dividendo Creciente ---
    if dividend_yield and dividend_yield > 0:
        if dividend_growing:
            dg_text = "✅ Los datos históricos sugieren que esta empresa **ha mantenido o aumentado sus dividendos** en los últimos años, siguiendo el patrón de los Dividend Aristocrats y Dividend Kings. Empresas como J&J, PG y Coca-Cola llevan más de 25 años incrementando el dividendo ininterrumpidamente."
            dg_status = "success"
        else:
            dg_text = "⚠️ Los datos disponibles no confirman una trayectoria clara de crecimiento de dividendos. Puede deberse a recortes previos, estabilización, o datos incompletos. Se recomienda verificar el historial de dividendos directamente en la fuente del broker."
            dg_status = "warning"
    else:
        dg_text = "Este activo no paga dividendos, por lo que no aplica el análisis de crecimiento de dividendos."
        dg_status = "neutral"

    sections.append({
        "title": "Dividendo Creciente (Dividend Growth)",
        "icon": "fa-arrow-trend-up",
        "content": dg_text,
        "value": "Sí ✅" if dividend_growing else ("No ⚠️" if (dividend_yield and dividend_yield > 0) else "N/A"),
        "status": dg_status
    })

    # --- Solidez de los fundamentos (FCF + Margen) ---
    fcf_yield = asset.get("fcf_yield")
    fcf_ok = fcf_yield is not None and fcf_yield > 0.02
    margin_ok = profit_margin is not None and profit_margin > 0.10
    debt_ok = debt_to_equity is not None and debt_to_equity < 1.0

    pillars = []
    if fcf_ok: pillars.append("FCF positivo y sostenible")
    if margin_ok: pillars.append(f"margen neto del {profit_margin*100:.0f}%")
    if debt_ok: pillars.append(f"baja deuda (D/E: {debt_to_equity:.2f}x)")

    if len(pillars) >= 2:
        sol_text = f"Los fundamentos de la empresa son **sólidos**: {', '.join(pillars)}. Esto respalda la capacidad de mantener y hacer crecer el dividendo en el largo plazo, incluso en entornos económicos adversos."
        sol_status = "success"
    elif len(pillars) == 1:
        sol_text = f"La empresa presenta **algunos pilares sólidos** ({', '.join(pillars)}), pero no cumple todos los criterios de robustez fundamental para Dividend Growth Investing. Se recomienda monitorear la evolución de los indicadores faltantes."
        sol_status = "neutral"
    else:
        sol_text = "Los datos disponibles no permiten confirmar la solidez fundamental necesaria para una tesis de Dividend Growth estable. Puede deberse a datos faltantes o a una empresa con fundamentos más débiles."
        sol_status = "warning"

    sections.append({
        "title": "Solidez Fundamental (Pilar del DGI)",
        "icon": "fa-landmark-flag",
        "content": sol_text,
        "value": f"{len(pillars)}/3 pilares",
        "status": sol_status
    })

    return sections


# ============================================================
#   ESTRATEGIAS DE MEDIANO PLAZO (6-12 meses)
# ============================================================

def build_earnings_revision_analysis(asset, currency):
    """
    Earnings Revision Strategy.
    Evalúa revisiones positivas del EPS, consensus de analistas y upside de precio objetivo.
    """
    sections = []

    eps_revision = asset.get("eps_revision_signal")
    analyst_consensus = asset.get("analyst_consensus")
    analyst_count = asset.get("analyst_count")
    target_upside = asset.get("target_upside_pct")
    target_mean = asset.get("target_mean_price")
    eps_growth = asset.get("eps_growth")
    revenue_growth = asset.get("revenue_growth")

    # --- Revisión de EPS (Forward vs Trailing) ---
    if eps_revision is not None:
        er_pct = eps_revision * 100
        if eps_revision > 0.10:
            er_text = (
                f"Se detecta una **revisión alcista del EPS del +{er_pct:.1f}%**: el EPS forward supera al trailing en esa magnitud. "
                f"Las revisiones positivas de EPS son una de las señales más predictivas del rendimiento accionario en horizontes de 6-12 meses, "
                f"ya que reflejan que los analistas han mejorado sus expectativas de ganancias futuras. "
                f"Estrategias cuantitativas como la de Zacks demuestran que las revisiones positivas preceden retornos superiores al mercado."
            )
            er_status = "success"
        elif eps_revision > 0:
            er_text = f"La **revisión del EPS muestra una mejora moderada (+{er_pct:.1f}%)**. El consenso de analistas proyecta ganancias levemente superiores a las actuales, señal constructiva aunque sin una aceleración marcada."
            er_status = "neutral"
        elif eps_revision > -0.10:
            er_text = f"La revisión del EPS indica una **leve compresión esperada ({er_pct:.1f}%)**. Las perspectivas de ganancias son algo inferiores al período anterior, lo que puede reflejar presiones en márgenes o un contexto sectorial más desafiante."
            er_status = "warning"
        else:
            er_text = f"Las estimaciones de EPS muestran una **revisión a la baja significativa ({er_pct:.1f}%)**. Cuando los analistas reducen masivamente sus pronósticos, históricamente el precio tiende a ajustarse en la misma dirección. Señal de alerta para el mediano plazo."
            er_status = "danger"
    else:
        er_text = "No se dispone de datos de EPS forward para este activo. Puede deberse a que es cripto, un CEDEAR sin cobertura directa de analistas, o falta de datos en la fuente."
        er_status = "neutral"

    sections.append({
        "title": "Revisión de EPS (Forward vs Trailing)",
        "icon": "fa-chart-bar",
        "content": er_text,
        "value": f"{eps_revision*100:+.1f}%" if eps_revision is not None else "N/D",
        "status": er_status
    })

    # --- Consensus de Analistas ---
    if analyst_consensus is not None and analyst_count is not None and analyst_count > 0:
        # yfinance devuelve: 1.0=Strong Buy, 2.0=Buy, 3.0=Hold, 4.0=Underperform, 5.0=Sell
        consensus_label = {1: "Compra Fuerte", 2: "Compra", 3: "Mantener", 4: "Bajo Rendimiento", 5: "Vender"}
        label = consensus_label.get(round(analyst_consensus), "")
        if analyst_consensus <= 1.5:
            ac_text = f"El consenso de **{analyst_count} analistas** es **{label} ({analyst_consensus:.1f}/5.0)** — señal fuertemente positiva. Un consenso de compra fuerte amplificado por un gran número de analistas reduce el sesgo individual y otorga mayor confianza a la recomendación."
            ac_status = "success"
        elif analyst_consensus <= 2.5:
            ac_text = f"El consenso de **{analyst_count} analistas** es **{label} ({analyst_consensus:.1f}/5.0)** — señal positiva. La mayoría de los profesionales recomienda incorporar el activo en los próximos 6-12 meses."
            ac_status = "success"
        elif analyst_consensus <= 3.2:
            ac_text = f"El consenso de **{analyst_count} analistas** es **{label} ({analyst_consensus:.1f}/5.0)** — señal neutral. No hay convicción clara de compra ni venta por parte del mercado profesional."
            ac_status = "neutral"
        else:
            ac_text = f"El consenso de **{analyst_count} analistas** es **{label} ({analyst_consensus:.1f}/5.0)** — señal negativa. Los analistas institucionales en su mayoría no recomiendan el activo en este momento para el mediano plazo."
            ac_status = "warning"
    else:
        ac_text = "No hay cobertura de analistas disponible para este activo en este período. Esto es frecuente en activos no estadounidenses, cripto y en algunos CEDEARs."
        ac_status = "neutral"

    sections.append({
        "title": "Consensus de Analistas",
        "icon": "fa-users-line",
        "content": ac_text,
        "value": f"{analyst_consensus:.1f}/5.0 ({analyst_count} analistas)" if analyst_consensus and analyst_count else "Sin cobertura",
        "status": ac_status
    })

    # --- Precio Objetivo (Upside) ---
    if target_upside is not None:
        up_pct = target_upside * 100
        if target_upside > 0.15:
            tu_text = f"El **precio objetivo medio de analistas** (${target_mean:,.2f}) implica un **upside del +{up_pct:.1f}%** sobre el precio actual. Un upside superior al 15% desde el consenso de analistas es una de las señales más directas de que el mercado profesional considera el activo subvalorado para el mediano plazo."
            tu_status = "success"
        elif target_upside > 0.05:
            tu_text = f"El precio objetivo de analistas implica un **upside moderado del +{up_pct:.1f}%** — los analistas ven algo de valor por encima del precio actual, pero sin un potencial disruptivo."
            tu_status = "neutral"
        elif target_upside >= 0:
            tu_text = f"El precio objetivo de analistas está apenas un **+{up_pct:.1f}%** por encima del precio actual. El potencial de upside es limitado desde el consenso profesional actual."
            tu_status = "warning"
        else:
            tu_text = f"El precio objetivo de analistas está un **{up_pct:.1f}%** por debajo del precio actual (downside). Los analistas consideran que el activo está sobrevalorado respecto a sus fundamentos de mediano plazo."
            tu_status = "danger"
    else:
        tu_text = "No se dispone de precio objetivo de analistas para este activo. Frecuente en cripto, activos argentinos locales y algunos CEDEARs."
        tu_status = "neutral"

    sections.append({
        "title": "Precio Objetivo y Upside Potencial",
        "icon": "fa-bullseye",
        "content": tu_text,
        "value": f"+{target_upside*100:.1f}% upside" if target_upside is not None else "N/D",
        "status": tu_status
    })

    # --- Crecimiento de EPS e Ingresos ---
    if eps_growth is not None or revenue_growth is not None:
        parts = []
        if eps_growth is not None:
            parts.append(f"EPS creció un **{eps_growth*100:+.1f}% interanual**")
        if revenue_growth is not None:
            parts.append(f"ingresos crecieron un **{revenue_growth*100:+.1f}% interanual**")
        growth_text = " y ".join(parts) + "."
        both_positive = (eps_growth or 0) > 0.05 and (revenue_growth or 0) > 0.05
        eg_text = (
            f"En el último trimestre {growth_text} "
            + ("Ambos indicadores en expansión es la señal más clara de un ciclo de ganancias positivo que típicamente acompaña apreciaciones de precio en los siguientes 6-12 meses."
               if both_positive else
               "Un crecimiento desigual puede indicar mejoras de eficiencia o presiones en alguno de los dos vectores del negocio.")
        )
        eg_status = "success" if both_positive else "neutral"
    else:
        eg_text = "No se dispone de datos de crecimiento trimestral de EPS e ingresos. Para activos sin cobertura de analistas (cripto, locales) este indicador puede obtenerse de los reportes directos de la empresa."
        eg_status = "neutral"

    sections.append({
        "title": "Crecimiento de EPS e Ingresos (Trim. YoY)",
        "icon": "fa-arrow-up-right-dots",
        "content": eg_text,
        "value": f"EPS {eps_growth*100:+.1f}%" if eps_growth is not None else "N/D",
        "status": eg_status
    })

    return sections


def build_can_slim_analysis(asset, currency):
    """
    CAN SLIM (William O'Neil) — Combina análisis fundamental y técnico para mediano plazo.
    C: Current earnings, A: Annual earnings growth, N: New (product/high), S: Supply/Demand,
    L: Leader, I: Institutional, M: Market direction.
    """
    sections = []

    eps_growth = asset.get("eps_growth")
    revenue_growth = asset.get("revenue_growth")
    rsi = asset.get("rsi", 50.0) or 50.0
    ret_3m = asset.get("ret_3m", 0.0) or 0.0
    ret_12m = asset.get("ret_12m", 0.0) or 0.0
    roe = asset.get("roe")
    vol_short_vs_long = asset.get("vol_short_vs_long", 1.0) or 1.0
    sharpe = asset.get("sharpe", 0.0) or 0.0
    analyst_consensus = asset.get("analyst_consensus")
    ema_cross_signal = asset.get("ema_cross_signal", 0.0) or 0.0

    # C — Current Quarterly Earnings (EPS trimestral)
    if eps_growth is not None:
        eg_pct = eps_growth * 100
        if eps_growth >= 0.25:
            c_text = f"**C (Current Earnings):** El EPS trimestral creció **+{eg_pct:.0f}% interanual** — supera el umbral mínimo del 25% que O'Neil exige para los mejores candidatos. Esta aceleración demuestra que el negocio está en fase de expansión activa."
            c_status = "success"
        elif eps_growth > 0:
            c_text = f"**C (Current Earnings):** El EPS trimestral creció **+{eg_pct:.0f}% interanual** — positivo, pero por debajo del umbral ideal del 25% que O'Neil considera señal de fuerza. El negocio avanza, aunque sin la aceleración óptima para CAN SLIM."
            c_status = "neutral"
        else:
            c_text = f"**C (Current Earnings):** El EPS trimestral cayó **{eg_pct:.0f}% interanual** — señal de alerta. O'Neil descartaría este activo en la selección CAN SLIM por falta de aceleración de ganancias."
            c_status = "warning"
    else:
        c_text = "**C (Current Earnings):** Sin datos trimestrales disponibles. Este componente no puede evaluarse para este activo (frecuente en cripto y activos sin cobertura de analistas)."
        c_status = "neutral"
    sections.append({"title": "C — Ganancias Trimestrales (Current Earnings)", "icon": "fa-c", "content": c_text,
                     "value": f"{eps_growth*100:+.0f}%" if eps_growth is not None else "N/D", "status": c_status})

    # A — Annual Earnings Growth
    if ret_12m != 0:
        ret_pct = ret_12m * 100
        if ret_12m > 0.20:
            a_text = f"**A (Annual Earnings):** El retorno de precio anual es **+{ret_pct:.0f}%**, consistente con empresas de alto crecimiento anual. O'Neil busca empresas con crecimiento anual de ganancias superior al 25% durante al menos 3 años consecutivos."
            a_status = "success"
        elif ret_12m > 0:
            a_text = f"**A (Annual Earnings):** El retorno anual es **+{ret_pct:.0f}%** — crecimiento moderado. Para CAN SLIM, lo ideal es ver aceleración progresiva en los retornos anuales."
            a_status = "neutral"
        else:
            a_text = f"**A (Annual Earnings):** El retorno anual es **{ret_pct:.0f}%** — señal de alerta. O'Neil filtra empresas cuyas ganancias no muestran crecimiento real en términos anuales."
            a_status = "warning"
    else:
        a_text = "**A (Annual Earnings):** Sin datos de retorno anual disponibles."
        a_status = "neutral"
    sections.append({"title": "A — Crecimiento Anual de Ganancias", "icon": "fa-a", "content": a_text,
                     "value": f"{ret_12m*100:+.0f}% (12M)" if ret_12m else "N/D", "status": a_status})

    # S — Supply & Demand (volumen y precio)
    if vol_short_vs_long < 0.85:
        s_text = f"**S (Supply & Demand):** La volatilidad de corto plazo es significativamente menor que la de largo plazo (ratio: {vol_short_vs_long:.2f}x), indicando **acumulación institucional tranquila** — patrón característico de los mejores setups de CAN SLIM antes de una ruptura alcista."
        s_status = "success"
    elif vol_short_vs_long <= 1.10:
        s_text = f"**S (Supply & Demand):** Ratio de volatilidad corta/larga de {vol_short_vs_long:.2f}x — equilibrio normal entre oferta y demanda. No se detectan señales claras de acumulación ni distribución institucional masiva."
        s_status = "neutral"
    else:
        s_text = f"**S (Supply & Demand):** La volatilidad de corto plazo supera a la de largo plazo (ratio: {vol_short_vs_long:.2f}x), sugiriendo **distribución o mayor incertidumbre reciente** — señal de cautela dentro del framework CAN SLIM."
        s_status = "warning"
    sections.append({"title": "S — Oferta y Demanda (Volatilidad/Volumen)", "icon": "fa-s", "content": s_text,
                     "value": f"{vol_short_vs_long:.2f}x", "status": s_status})

    # L — Leader or Laggard (fuerza relativa / RSI)
    if rsi >= 60:
        l_text = f"**L (Leader):** El RSI de {rsi:.0f} confirma que el activo tiene **momentum de precio fuerte**: es un líder de mercado, no un rezagado. O'Neil prioriza los primeros 1-2 activos de cada sector, no los más rezagados aunque parezcan baratos."
        l_status = "success"
    elif rsi >= 45:
        l_text = f"**L (Leader):** RSI de {rsi:.0f} — el activo no destaca como líder claro ni como rezagado. Para CAN SLIM, el liderazgo de precio relativo es clave: buscar activos en el percentil 80+ de fuerza relativa."
        l_status = "neutral"
    else:
        l_text = f"**L (Leader):** RSI de {rsi:.0f} — el activo muestra debilidad relativa. O'Neil considera que comprar activos débiles esperando recuperación ('value traps') es una de las principales causas de pérdida en los inversores de mediano plazo."
        l_status = "warning"
    sections.append({"title": "L — Liderazgo de Mercado (Leader)", "icon": "fa-l", "content": l_text,
                     "value": f"RSI {rsi:.0f}", "status": l_status})

    # I — Institutional Sponsorship (consensus proxy)
    if analyst_consensus is not None:
        if analyst_consensus <= 2.0:
            i_text = f"**I (Institutional Sponsorship):** El consenso de analistas ({analyst_consensus:.1f}/5.0) representa una fuerte cobertura institucional positiva. Las instituciones suelen moverse antes que el precio: cuando el institutional sponsorship aumenta, el precio tiende a seguir."
            i_status = "success"
        elif analyst_consensus <= 3.0:
            i_text = f"**I (Institutional Sponsorship):** Cobertura institucional neutral ({analyst_consensus:.1f}/5.0). No hay señales claras de acumulación ni reducción de posiciones institucionales."
            i_status = "neutral"
        else:
            i_text = f"**I (Institutional Sponsorship):** Señal negativa ({analyst_consensus:.1f}/5.0). En el framework CAN SLIM, la falta de respaldo institucional es un filtro de exclusión importante."
            i_status = "warning"
    else:
        i_text = "**I (Institutional Sponsorship):** Sin cobertura de analistas disponible. Para activos argentinos locales y cripto, el 'sponsorship' se mide mejor por el volumen relativo y la acumulación en cadena."
        i_status = "neutral"
    sections.append({"title": "I — Respaldo Institucional (Institutional)", "icon": "fa-i", "content": i_text,
                     "value": f"{analyst_consensus:.1f}/5" if analyst_consensus else "Sin datos", "status": i_status})

    # M — Market Direction (EMA trend signal as proxy)
    if ema_cross_signal > 0.05:
        m_text = f"**M (Market Direction):** El cruce EMA 50/200 señala un entorno de mercado **alcista** (EMA50 supera a EMA200 en {ema_cross_signal*100:.1f}%). O'Neil insiste: 3 de cada 4 acciones siguen la dirección del mercado general. Operar a favor de la tendencia macro mejora significativamente las probabilidades de éxito."
        m_status = "success"
    elif ema_cross_signal > -0.03:
        m_text = f"**M (Market Direction):** El diferencial EMA 50/200 es neutro ({ema_cross_signal*100:.1f}%). El mercado no muestra una tendencia clara que potencie o dificulte el trade. Se recomienda precaución con el tamaño de la posición."
        m_status = "neutral"
    else:
        m_text = f"**M (Market Direction):** El cruce EMA señala una tendencia de mercado **bajista** ({ema_cross_signal*100:.1f}%). O'Neil prohíbe rotundamente comprar en mercados bajistas: 'Si el mercado baja, la mejor cartera no sirve'."
        m_status = "warning"
    sections.append({"title": "M — Dirección del Mercado (Market)", "icon": "fa-m", "content": m_text,
                     "value": f"{ema_cross_signal*100:+.1f}%", "status": m_status})

    return sections


def build_relative_strength_analysis(asset, currency):
    """
    Relative Strength + Market Leadership.
    Prioriza activos líderes dentro de los sectores más fuertes del mercado.
    """
    sections = []

    rsi = asset.get("rsi", 50.0) or 50.0
    ret_1m = asset.get("ret_1m", 0.0) or 0.0
    ret_3m = asset.get("ret_3m", 0.0) or 0.0
    ret_12m = asset.get("ret_12m", 0.0) or 0.0
    ema_cross_signal = asset.get("ema_cross_signal", 0.0) or 0.0
    vol_short_vs_long = asset.get("vol_short_vs_long", 1.0) or 1.0
    volatility = asset.get("volatility", 0.3) or 0.3
    category = asset.get("category", "")
    momentum_accel = asset.get("momentum_accel", 0.0) or 0.0

    # --- Fuerza Relativa (RSI + retornos) ---
    rs_score = 0
    if rsi >= 60: rs_score += 2
    elif rsi >= 50: rs_score += 1
    if ret_3m > 0.10: rs_score += 2
    elif ret_3m > 0: rs_score += 1
    if ret_12m > 0.20: rs_score += 2
    elif ret_12m > 0: rs_score += 1

    if rs_score >= 5:
        rs_text = f"La **fuerza relativa del activo es muy alta** (score interno: {rs_score}/6): RSI={rsi:.0f}, retorno 3M={ret_3m*100:+.1f}%, retorno 12M={ret_12m*100:+.1f}%. El activo muestra momentum sostenido en múltiples ventanas temporales, compatible con los líderes de su sector."
        rs_status = "success"
    elif rs_score >= 3:
        rs_text = f"La **fuerza relativa es moderada** (score: {rs_score}/6): el activo muestra solidez en algunas ventanas pero no domina todas. RSI={rsi:.0f}, 3M={ret_3m*100:+.1f}%."
        rs_status = "neutral"
    else:
        rs_text = f"La **fuerza relativa es débil** (score: {rs_score}/6). El activo no evidencia momentum sostenido. RSI={rsi:.0f}, 3M={ret_3m*100:+.1f}%. Desde la perspectiva de Relative Strength Investing, se priorizan activos en el percentil 80+ de fuerza."
        rs_status = "warning"

    sections.append({
        "title": "Fuerza Relativa (Relative Strength)",
        "icon": "fa-ranking-star",
        "content": rs_text,
        "value": f"Score {rs_score}/6",
        "status": rs_status
    })

    # --- Tendencia vs Índice (EMA Cross como proxy) ---
    if ema_cross_signal > 0.08:
        ti_text = f"El activo supera significativamente su media de largo plazo (cruce EMA: +{ema_cross_signal*100:.1f}%), situándolo **por encima** del benchmark técnico. Esta posición estructural es lo que buscan los gestores de momentum: empresas que lideran su índice de referencia."
        ti_status = "success"
    elif ema_cross_signal > 0:
        ti_text = f"El activo está levemente por encima de su tendencia de larga data (cruce EMA: +{ema_cross_signal*100:.1f}%). No es líder dominante, pero muestra resiliencia relativa."
        ti_status = "neutral"
    else:
        ti_text = f"El activo está por debajo de su media de largo plazo (cruce EMA: {ema_cross_signal*100:.1f}%), indicando rezago relativo. La selección por fuerza relativa excluiría esta posición en favor de activos más fuertes del mismo sector."
        ti_status = "warning"

    sections.append({
        "title": "Tendencia vs. Media de Largo Plazo",
        "icon": "fa-chart-line",
        "content": ti_text,
        "value": f"{ema_cross_signal*100:+.1f}%",
        "status": ti_status
    })

    # --- Aceleración de Momentum ---
    if momentum_accel > 0.05:
        ma_text = f"El **momentum se está acelerando** (+{momentum_accel*100:.1f}%): el retorno de corto plazo supera al de mediano plazo, señal de que el activo está ganando fuerza de forma progresiva. Los líderes de mercado suelen mostrar esta dinámica antes de sus mayores etapas de apreciación."
        ma_status = "success"
    elif momentum_accel >= -0.05:
        ma_text = f"El momentum se mantiene **estable** ({momentum_accel*100:+.1f}%). La velocidad de apreciación no muestra ni aceleración ni desaceleración significativa."
        ma_status = "neutral"
    else:
        ma_text = f"El momentum **se está desacelerando** ({momentum_accel*100:.1f}%). El activo pierde velocidad de apreciación, lo que puede preceder una corrección o consolidación."
        ma_status = "warning"

    sections.append({
        "title": "Aceleración de Momentum",
        "icon": "fa-gauge-simple-high",
        "content": ma_text,
        "value": f"{momentum_accel*100:+.1f}%",
        "status": ma_status
    })

    # Sector context by category
    sector_ctx = {
        "sp500": "El S&P 500 engloba los 500 mayores activos de EE.UU. En estrategias de liderazgo sectorial, se priorizan los sectores con mayor flujo de capital institucional (tecnología, salud, defensa, energía), seleccionando las empresas con mayor fuerza relativa dentro de cada uno.",
        "cedears": "Los CEDEARs representan acciones internacionales cotizando en pesos. Aplica la misma lógica de liderazgo sectorial global, con el bonus de cobertura cambiaria implícita frente al dólar (CCL).",
        "merval": "El Merval es el índice local argentino. La dinámica sectorial interna difiere de los mercados desarrollados: energía, bancos y construcción tienden a liderar en ciclos de estabilización macro.",
        "crypto": "En cripto, el liderazgo de mercado se analiza mediante la dominancia de Bitcoin (BTC.D): cuando BTC lidera, los altcoins suelen quedarse atrás. Cuando BTC entra en lateralización, los altcoins con mayor fuerza relativa tienden a destacar (altseason).",
    }
    sc_text = sector_ctx.get(category, "Contexto sectorial no especificado para esta categoría de activo.")

    sections.append({
        "title": "Liderazgo Sectorial (Market Leadership)",
        "icon": "fa-sitemap",
        "content": sc_text,
        "value": category.upper() if category else "N/D",
        "status": "neutral"
    })

    return sections


def build_garp_analysis(asset, currency):
    """
    GARP — Growth At a Reasonable Price.
    Combina crecimiento de EPS con valuación razonable (PEG, PER, FCF, ROE, deuda moderada).
    """
    sections = []

    peg_ratio = asset.get("peg_ratio")
    eps_growth = asset.get("eps_growth")
    revenue_growth = asset.get("revenue_growth")
    pe = asset.get("pe_ratio")
    forward_pe = asset.get("forward_pe")
    roe = asset.get("roe")
    fcf_yield = asset.get("fcf_yield")
    debt_to_equity = asset.get("debt_to_equity")

    # --- PEG Ratio ---
    if peg_ratio is not None and peg_ratio > 0:
        if peg_ratio < 1.0:
            peg_text = (
                f"El **PEG Ratio de {peg_ratio:.2f}x** es excelente para GARP (< 1.0x). "
                f"El PEG = PER / Crecimiento esperado del EPS: un valor menor a 1 indica que el precio paga menos que el crecimiento proyectado, "
                f"el escenario ideal para los inversores GARP como Peter Lynch. "
                f"Lynch consideraba que pagar 1x el crecimiento era 'precio justo' y bajo 1x una ganga."
            )
            peg_status = "success"
        elif peg_ratio < 2.0:
            peg_text = f"El **PEG de {peg_ratio:.2f}x** es razonable (1-2x). El inversionista paga algo más que el crecimiento esperado, pero no está pagando una prima excesiva. Zona de valuación aceptable para GARP."
            peg_status = "neutral"
        else:
            peg_text = f"El **PEG de {peg_ratio:.2f}x** es elevado (> 2x). El precio incorpora demasiado crecimiento futuro para el ritmo actual. Desde la perspectiva GARP, existe riesgo de decepción si el crecimiento real no alcanza las expectativas implícitas en el precio."
            peg_status = "warning"
    elif peg_ratio is not None and peg_ratio < 0:
        peg_text = f"El **PEG Ratio es negativo** ({peg_ratio:.2f}x), lo que indica pérdidas netas actuales o contracción de EPS. Este activo no encaja en la definición clásica de GARP dado que el crecimiento esperado es negativo."
        peg_status = "danger"
    else:
        peg_text = "El **PEG Ratio no está disponible** para este activo. Para cripto y activos sin cobertura de analistas, se compensa utilizando el crecimiento histórico de precio como proxy del crecimiento esperado."
        peg_status = "neutral"

    sections.append({
        "title": "PEG Ratio (Crecimiento a Precio Razonable)",
        "icon": "fa-balance-scale",
        "content": peg_text,
        "value": f"{peg_ratio:.2f}x" if peg_ratio else "N/D",
        "status": peg_status
    })

    # --- Crecimiento esperado EPS ---
    if eps_growth is not None:
        eg_pct = eps_growth * 100
        if eps_growth > 0.15:
            eg_text = f"El **crecimiento del EPS es del +{eg_pct:.0f}% interanual** — sólido y compatible con el perfil GARP. Un crecimiento de EPS superior al 15% es el mínimo de referencia para que la valuación premium se justifique en el mediano plazo."
            eg_status = "success"
        elif eps_growth > 0:
            eg_text = f"El crecimiento del EPS es **moderado (+{eg_pct:.0f}%)**. Positivo pero por debajo del umbral ideal para GARP. Puede funcionar si el PEG ratio es suficientemente bajo."
            eg_status = "neutral"
        else:
            eg_text = f"El EPS muestra **contracción ({eg_pct:.0f}%)**. GARP exige crecimiento real de ganancias: sin crecimiento, la G de GARP desaparece y el PER pierde su justificación."
            eg_status = "warning"
    else:
        eg_text = "Datos de crecimiento de EPS no disponibles para este activo."
        eg_status = "neutral"

    sections.append({
        "title": "Crecimiento Esperado del EPS",
        "icon": "fa-up-long",
        "content": eg_text,
        "value": f"{eps_growth*100:+.0f}% EPS" if eps_growth is not None else "N/D",
        "status": eg_status
    })

    # --- PER Forward vs Trailing ---
    if forward_pe is not None and pe is not None:
        pe_trend = forward_pe - pe
        if pe_trend < -2:
            pe_text = f"El **PER forward ({forward_pe:.1f}x) es menor al trailing ({pe:.1f}x)** en {abs(pe_trend):.1f} puntos: los analistas esperan que las ganancias aumenten en los próximos 12 meses, comprimiendo el múltiplo. Es la señal perfecta de GARP: valuación decreciente por crecimiento."
            pe_status = "success"
        elif pe_trend <= 2:
            pe_text = f"El PER forward ({forward_pe:.1f}x) y trailing ({pe:.1f}x) son similares: las ganancias esperadas son consistentes con las actuales, sin gran expansión ni contracción del múltiplo."
            pe_status = "neutral"
        else:
            pe_text = f"El PER forward ({forward_pe:.1f}x) es mayor al trailing ({pe:.1f}x): los analistas esperan menores ganancias en los próximos 12 meses, lo que implica una expansión del múltiplo sin crecimiento. Señal negativa para GARP."
            pe_status = "warning"
    elif pe is not None:
        pe_text = f"PER actual: **{pe:.1f}x**. Sin dato de PER forward no se puede estimar la dirección de las ganancias esperadas — dato fundamental en el análisis GARP."
        pe_status = "neutral"
    else:
        pe_text = "Sin datos de PER disponibles para este activo."
        pe_status = "neutral"

    sections.append({
        "title": "PER Forward vs. Trailing",
        "icon": "fa-calendar-check",
        "content": pe_text,
        "value": f"Forward: {forward_pe:.1f}x" if forward_pe else "N/D",
        "status": pe_status
    })

    # --- ROE + Deuda relevante para GARP ---
    garp_pillars = []
    if roe is not None and roe > 0.12:
        garp_pillars.append(f"ROE sólido del {roe*100:.0f}%")
    if fcf_yield is not None and fcf_yield > 0.02:
        garp_pillars.append(f"FCF Yield positivo del {fcf_yield*100:.1f}%")
    if debt_to_equity is not None and debt_to_equity < 1.5:
        garp_pillars.append(f"Deuda moderada (D/E: {debt_to_equity:.2f}x)")

    if len(garp_pillars) >= 2:
        garp_text = f"La empresa cumple con las condiciones de calidad fundamentales del GARP: {', '.join(garp_pillars)}. Estos pilares permiten que el crecimiento sea sostenible sin depender de apalancamiento excesivo."
        garp_status = "success"
    elif len(garp_pillars) == 1:
        garp_text = f"Cumple parcialmente los pilares de calidad del GARP: {', '.join(garp_pillars)}. Los inversores GARP exigen crecimiento y calidad simultáneamente."
        garp_status = "neutral"
    else:
        garp_text = "Los datos disponibles no permiten confirmar los pilares de calidad del GARP (ROE, FCF, deuda). Esto puede deberse a ausencia de datos o a fundamentos más débiles que el estilo requiere."
        garp_status = "warning"

    sections.append({
        "title": "Calidad Fundamental (ROE + FCF + Deuda)",
        "icon": "fa-gem",
        "content": garp_text,
        "value": f"{len(garp_pillars)}/3 pilares",
        "status": garp_status
    })

    return sections
