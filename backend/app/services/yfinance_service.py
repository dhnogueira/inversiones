import os
import json
import time
import pandas as pd
import numpy as np
import yfinance as yf
from app.config import CACHE_DIR

# Ticker lists
SP500_TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "BRK-B", "LLY", "AVGO", "JPM", "TSLA", "XOM", "UNH", "PG", "V", "MA", "HD", "COST", "MRK", "ABBV"]
CEDEAR_TICKERS = ["AAPL.BA", "MSFT.BA", "TSLA.BA", "MELI.BA", "KO.BA", "NVDA.BA", "AMZN.BA", "META.BA", "GOOGL.BA", "XOM.BA", "BABA.BA", "VALE.BA", "PBR.BA", "GGLD.BA", "DESP.BA"]
MERVAL_TICKERS = ["YPFD.BA", "GGAL.BA", "PAMP.BA", "ALUA.BA", "TXAR.BA", "BMA.BA", "CEPU.BA", "TGSU2.BA", "EDN.BA", "LOMA.BA", "CRES.BA", "TECO2.BA", "SUPV.BA", "VALO.BA", "BYMA.BA"]
CRYPTO_TICKERS = ["BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD", "AVAX-USD", "LINK-USD", "DOT-USD"]
BONO_TICKERS = ["AL30.BA", "GD30.BA", "AL29.BA", "GD29.BA", "AL35.BA", "GD35.BA", "AE38.BA", "GD38.BA", "AL41.BA", "GD41.BA"]

def calculate_rsi(prices, period=14):
    deltas = prices.diff()
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0
    rsi = np.zeros_like(prices)
    rsi[:period] = 100. - 100. / (1. + rs)

    for i in range(period, len(prices)):
        delta = deltas.iloc[i]
        if delta > 0:
            upval = delta
            downval = 0.
        else:
            upval = 0.
            downval = -delta
        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period
        rs = up / down if down != 0 else 0
        rsi[i] = 100. - 100. / (1. + rs)
    return rsi

def compute_volume_profile(prices, volumes, bins=10):
    """
    Calcula el Point of Control (POC), es decir, el precio del cluster con mayor volumen.
    """
    try:
        p_min, p_max = float(prices.min()), float(prices.max())
        if p_min == p_max:
            return p_min
        
        bin_edges = np.linspace(p_min, p_max, bins + 1)
        bin_volumes = np.zeros(bins)
        
        for p, v in zip(prices, volumes):
            # Encontrar el bin correspondiente
            idx = np.searchsorted(bin_edges, p) - 1
            idx = max(0, min(idx, bins - 1))
            bin_volumes[idx] += v
            
        max_idx = np.argmax(bin_volumes)
        # Retornar el punto medio del bin con mayor volumen
        return float((bin_edges[max_idx] + bin_edges[max_idx + 1]) / 2.0)
    except Exception:
        return float(prices.iloc[-1])

def fetch_fundamental_metrics(ticker, category):
    """
    Obtiene métricas fundamentales de largo plazo mediante yf.Ticker.info.
    Solo relevante para acciones (sp500, cedears, merval). Retorna dict vacío para cripto/bonos.
    """
    if category in ("crypto", "bonos", "letras"):
        return {}
    try:
        info = yf.Ticker(ticker).info
        pe = info.get("trailingPE") or info.get("forwardPE")
        pb = info.get("priceToBook")
        roe = info.get("returnOnEquity")
        fcf = info.get("freeCashflow")
        market_cap = info.get("marketCap")
        fcf_yield = round((fcf / market_cap), 4) if fcf and market_cap and market_cap > 0 else None
        debt_to_equity = info.get("debtToEquity")
        if debt_to_equity is not None:
            debt_to_equity = round(debt_to_equity / 100, 2)  # yfinance da D/E en %, normalizar a ratio
        dividend_yield = info.get("dividendYield")  # valor entre 0 y 1
        payout_ratio = info.get("payoutRatio")
        trailing_annual_div = info.get("trailingAnnualDividendRate", 0.0) or 0.0
        five_yr_avg_div = info.get("fiveYearAvgDividendYield")  # porcentual (eg: 1.5 = 1.5%)
        # Dividend growth: si el trailing > 0 y five_yr_avg > 0, estimar crecimiento
        div_growing = False
        if trailing_annual_div and trailing_annual_div > 0 and five_yr_avg_div and five_yr_avg_div > 0:
            current_yield_pct = (dividend_yield or 0) * 100
            div_growing = current_yield_pct >= five_yr_avg_div * 0.8  # conservador: al menos 80% del promedio
        profit_margins = info.get("profitMargins")
        operating_margins = info.get("operatingMargins")
        # --- Medium-term analyst and growth metrics ---
        peg_ratio = info.get("pegRatio")
        eps_growth = info.get("earningsGrowth")  # quarterly YoY
        revenue_growth = info.get("revenueGrowth")  # quarterly YoY
        analyst_consensus = info.get("recommendationMean")  # 1=Strong Buy, 5=Sell
        analyst_count = info.get("numberOfAnalystOpinions")
        target_mean = info.get("targetMeanPrice")
        target_high = info.get("targetHighPrice")
        forward_pe = info.get("forwardPE")
        trailing_eps = info.get("trailingEps")
        forward_eps = info.get("forwardEps")
        current_price_info = info.get("currentPrice") or info.get("regularMarketPrice")
        # Target upside from mean analyst target vs current price
        target_upside_pct = None
        if target_mean and current_price_info and current_price_info > 0:
            target_upside_pct = round((target_mean - current_price_info) / current_price_info, 4)
        # EPS revision: forward EPS vs trailing EPS, proxy for analyst upgrade
        eps_revision_signal = None
        if forward_eps and trailing_eps and trailing_eps > 0:
            eps_revision_signal = round((forward_eps - trailing_eps) / abs(trailing_eps), 4)
        return {
            "pe_ratio": round(float(pe), 1) if pe else None,
            "pb_ratio": round(float(pb), 2) if pb else None,
            "roe": round(float(roe), 4) if roe is not None else None,
            "fcf_yield": round(float(fcf_yield), 4) if fcf_yield is not None else None,
            "debt_to_equity": round(float(debt_to_equity), 2) if debt_to_equity is not None else None,
            "dividend_yield": round(float(dividend_yield), 4) if dividend_yield is not None else None,
            "payout_ratio": round(float(payout_ratio), 4) if payout_ratio is not None else None,
            "dividend_growing": div_growing,
            "profit_margin": round(float(profit_margins), 4) if profit_margins is not None else None,
            "operating_margin": round(float(operating_margins), 4) if operating_margins is not None else None,
            # Medium-term
            "peg_ratio": round(float(peg_ratio), 2) if peg_ratio else None,
            "eps_growth": round(float(eps_growth), 4) if eps_growth is not None else None,
            "revenue_growth": round(float(revenue_growth), 4) if revenue_growth is not None else None,
            "analyst_consensus": round(float(analyst_consensus), 2) if analyst_consensus is not None else None,
            "analyst_count": int(analyst_count) if analyst_count else None,
            "target_mean_price": round(float(target_mean), 2) if target_mean else None,
            "target_upside_pct": round(float(target_upside_pct), 4) if target_upside_pct is not None else None,
            "eps_revision_signal": round(float(eps_revision_signal), 4) if eps_revision_signal is not None else None,
            "forward_pe": round(float(forward_pe), 1) if forward_pe else None,
        }
    except Exception as e:
        return {}


def compute_asset_metrics(df, ticker, category):
    if df.empty or len(df) < 50:
        return None
    
    close = df['Close']
    current_price = float(close.iloc[-1])
    
    # Calculate returns
    ret_1m = float((close.iloc[-1] / close.iloc[-min(21, len(close))] - 1) if len(close) >= 21 else 0)
    ret_3m = float((close.iloc[-1] / close.iloc[-min(63, len(close))] - 1) if len(close) >= 63 else 0)
    ret_6m = float((close.iloc[-1] / close.iloc[-min(126, len(close))] - 1) if len(close) >= 126 else 0)
    ret_12m = float((close.iloc[-1] / close.iloc[-min(252, len(close))] - 1) if len(close) >= 250 else 0)
    
    # Calculate Volatility (annualized, 252 trading days)
    daily_returns = close.pct_change().dropna()
    volatility = float(daily_returns.std() * np.sqrt(252) if len(daily_returns) > 0 else 0)
    
    # Sharpe Ratio (using risk free rate 4% or 0.04)
    rf = 0.04
    ann_return = ret_12m if ret_12m != 0 else ret_6m * 2
    sharpe = float((ann_return - rf) / volatility if volatility > 0 else 0)
    
    # Technical Indicators
    ema_50_series = close.ewm(span=50, adjust=False).mean()
    ema_200_series = close.ewm(span=200, adjust=False).mean()
    ema_50 = float(ema_50_series.iloc[-1])
    ema_200 = float(ema_200_series.iloc[-1])
    
    # Dynamic EMA 200 slope over last 30 trading days
    if len(ema_200_series) >= 30:
        ema_200_slope = float((ema_200 - ema_200_series.iloc[-30]) / ema_200_series.iloc[-30])
    else:
        ema_200_slope = 0.0
        
    # Drawdown from peak (52-week or 252 trading days max)
    lookback_52w = min(252, len(close))
    high_52w = float(close.iloc[-lookback_52w:].max())
    drawdown_pct = float((high_52w - current_price) / high_52w) if high_52w > 0 else 0.0

    rsi_series = calculate_rsi(close)
    rsi = float(rsi_series[-1])
    
    # Trend signal (Golden Cross, Above 200, etc.)
    trend = "Alcista" if current_price > ema_200 else "Bajista"
    if ema_50 > ema_200 and close.iloc[-1] > ema_50:
        trend = "Fuerte Alcista"
    elif ema_50 < ema_200 and close.iloc[-1] < ema_50:
        trend = "Fuerte Bajista"
        
    # Soportes, resistencias y clusters de volumen
    lookback_days = min(90, len(close))
    close_recent = close.iloc[-lookback_days:]
    support = float(np.percentile(close_recent, 10))
    resistance = float(np.percentile(close_recent, 90))
    
    lookback_vol = min(100, len(close))
    prices_vol = close.iloc[-lookback_vol:]
    volumes_vol = df['Volume'].iloc[-lookback_vol:] if 'Volume' in df.columns else np.ones(lookback_vol)
    volume_cluster = compute_volume_profile(prices_vol, volumes_vol)

    # ---- MÉTRICAS MULTI-HORIZONTE DE TIMING ----

    # Aceleración de momentum: ret_1m - ret_3m
    # Positivo = acelerando (bueno para corto plazo); Negativo = desacelerando
    momentum_accel = float(ret_1m - ret_3m)

    # Señal de cruce EMA50/EMA200 (normalizada)
    # Positivo = Golden Cross zone (bullish medium-term); Negativo = Death Cross
    ema_cross_signal = float((ema_50 - ema_200) / ema_200 if ema_200 != 0 else 0)

    # Distancia porcentual al soporte (cercanía = oportunidad de compra en corto plazo)
    dist_to_support_pct = float((current_price - support) / current_price if current_price > 0 else 0)

    # Distancia porcentual a la resistencia (espacio de upside hasta próxima resistencia)
    dist_to_resistance_pct = float((resistance - current_price) / current_price if current_price > 0 else 0)

    # Ratio volatilidad corta (20d) vs larga (252d)
    # < 1.0 = volatilidad bajando (estabilización, bueno para corto plazo)
    # > 1.0 = volatilidad subiendo (riesgo creciente)
    vol_20d = float(daily_returns.iloc[-20:].std() * np.sqrt(252) if len(daily_returns) >= 20 else volatility)
    vol_short_vs_long = float(vol_20d / volatility if volatility > 0.001 else 1.0)

    return {
        "ticker": ticker,
        "name": ticker.replace(".BA", ""),
        "category": category,
        "price": current_price,
        "currency": "USD" if category in ["sp500", "crypto"] else "ARS",
        "ret_1m": ret_1m,
        "ret_3m": ret_3m,
        "ret_6m": ret_6m,
        "ret_12m": ret_12m,
        "volatility": volatility,
        "sharpe": sharpe,
        "rsi": rsi,
        "ema_50": ema_50,
        "ema_200": ema_200,
        "trend": trend,
        "ema_200_slope": round(ema_200_slope, 4),
        "high_52w": round(high_52w, 2),
        "drawdown_pct": round(drawdown_pct, 4),
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "volume_cluster": round(volume_cluster, 2),
        "momentum_accel": round(momentum_accel, 4),
        "ema_cross_signal": round(ema_cross_signal, 4),
        "dist_to_support_pct": round(dist_to_support_pct, 4),
        "dist_to_resistance_pct": round(dist_to_resistance_pct, 4),
        "vol_short_vs_long": round(vol_short_vs_long, 4),
        "timestamp": time.time()
    }

async def fetch_yfinance_market_data(force_refresh=False):
    cache_path = os.path.join(CACHE_DIR, "yfinance_market_data.json")
    
    # Evaluar validez del cache elemento por elemento según las reglas de la skill Caching
    if not force_refresh and os.path.exists(cache_path):
        try:
            with open(cache_path, "r") as f:
                cached = json.load(f)
            
            cached_data = cached.get("data", [])
            cache_timestamp = cached.get("timestamp", 0)
            now = time.time()
            
            # Verificar hora y día local para mercado
            import datetime
            dt = datetime.datetime.fromtimestamp(now)
            is_market_hours = (11 <= dt.hour < 17) and (dt.weekday() < 5)
            
            is_expired = False
            for asset in cached_data:
                cat = asset.get("category", "")
                age = now - asset.get("timestamp", cache_timestamp)
                
                if cat == "crypto":
                    # Criptomonedas: TTL de 5 minutos
                    if age > 300:
                        is_expired = True; break
                elif cat in ["sp500", "merval", "cedears"]:
                    # Acciones: 15 minutos en horario de mercado, o 12 horas fuera de mercado
                    ttl = 900 if is_market_hours else 43200
                    if age > ttl:
                        is_expired = True; break
                elif cat in ["bonos", "letras"]:
                    # Renta Fija: Persiste 24 horas
                    if age > 86400:
                        is_expired = True; break
            
            if not is_expired and len(cached_data) > 0:
                print("Cache de yfinance válido (aplicada regla de TTL dinámico por categorías).")
                return cached_data
                
        except Exception as e:
            print(f"Error parseando cache de yfinance: {e}")
            
    # If expired or force_refresh, fetch new data
    all_tickers = SP500_TICKERS + CEDEAR_TICKERS + MERVAL_TICKERS + CRYPTO_TICKERS + BONO_TICKERS
    
    # Download 2 years of historical daily data to guarantee enough trading days for 12m metrics (>252)
    print(f"Downloading data for {len(all_tickers)} tickers...")
    data = yf.download(all_tickers, period="2y", interval="1d", group_by="ticker", progress=False)
    
    results = []
    
    # Categories mapping
    categories = {}
    for t in SP500_TICKERS: categories[t] = "sp500"
    for t in CEDEAR_TICKERS: categories[t] = "cedears"
    for t in MERVAL_TICKERS: categories[t] = "merval"
    for t in CRYPTO_TICKERS: categories[t] = "crypto"
    for t in BONO_TICKERS: categories[t] = "bonos"
    
    for ticker in all_tickers:
        try:
            # yfinance returns multi-index if downloading multiple tickers
            df = data[ticker].dropna(subset=['Close'])
            category = categories[ticker]
            metrics = compute_asset_metrics(df, ticker, category)
            if metrics:
                fundamentals = fetch_fundamental_metrics(ticker, category)
                metrics.update(fundamentals)
                results.append(metrics)
        except Exception as e:
            print(f"Error processing {ticker}: {e}")
            
    # Save cache if we got decent results (at least 50% of expected tickers)
    if len(results) >= len(all_tickers) * 0.5:
        cache_data = {
            "timestamp": time.time(),
            "data": results
        }
        with open(cache_path, "w") as f:
            json.dump(cache_data, f)
    else:
        print(f"WARNING: Descarga de yfinance incompleta o fallida (sintetizados solo {len(results)}/{len(all_tickers)}).")
        if os.path.exists(cache_path):
            print("Cargando caché previo completo de yfinance como resguardo...")
            try:
                with open(cache_path, "r") as f:
                    cached = json.load(f)
                results = cached.get("data", [])
            except Exception as e:
                print(f"Error cargando caché previo de resguardo: {e}")
        
    return results

if __name__ == "__main__":
    import asyncio
    asyncio.run(fetch_yfinance_market_data(force_refresh=True))
