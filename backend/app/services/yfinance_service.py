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

def compute_asset_metrics(df, ticker, category):
    if df.empty or len(df) < 50:
        return None
    
    close = df['Close']
    current_price = float(close.iloc[-1])
    
    # Calculate returns
    ret_1m = float((close.iloc[-1] / close.iloc[-21] - 1) if len(close) >= 21 else 0)
    ret_3m = float((close.iloc[-1] / close.iloc[-63] - 1) if len(close) >= 63 else 0)
    ret_6m = float((close.iloc[-1] / close.iloc[-126] - 1) if len(close) >= 126 else 0)
    ret_12m = float((close.iloc[-1] / close.iloc[-252] - 1) if len(close) >= 252 else 0)
    
    # Calculate Volatility (annualized, 252 trading days)
    daily_returns = close.pct_change().dropna()
    volatility = float(daily_returns.std() * np.sqrt(252) if len(daily_returns) > 0 else 0)
    
    # Sharpe Ratio (using risk free rate 4% or 0.04)
    rf = 0.04
    ann_return = ret_12m if ret_12m != 0 else ret_6m * 2
    sharpe = float((ann_return - rf) / volatility if volatility > 0 else 0)
    
    # Technical Indicators
    ema_50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
    ema_200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])
    
    rsi_series = calculate_rsi(close)
    rsi = float(rsi_series[-1])
    
    # Trend signal (Golden Cross, Above 200, etc.)
    trend = "Alcista" if current_price > ema_200 else "Bajista"
    if ema_50 > ema_200 and close.iloc[-1] > ema_50:
        trend = "Fuerte Alcista"
    elif ema_50 < ema_200 and close.iloc[-1] < ema_50:
        trend = "Fuerte Bajista"
        
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
    
    # Download 1 year of historical daily data
    print(f"Downloading data for {len(all_tickers)} tickers...")
    data = yf.download(all_tickers, period="1y", interval="1d", group_by="ticker", progress=False)
    
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
                results.append(metrics)
        except Exception as e:
            print(f"Error processing {ticker}: {e}")
            
    # Save cache
    cache_data = {
        "timestamp": time.time(),
        "data": results
    }
    with open(cache_path, "w") as f:
        json.dump(cache_data, f)
        
    return results

if __name__ == "__main__":
    import asyncio
    asyncio.run(fetch_yfinance_market_data(force_refresh=True))
