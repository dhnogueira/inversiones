"""
data_providers.py — Motor de datos de mercado multi-fuente con fallback en cascada

Prioridad por clase de activo:
  sp500 / cedears / merval / bonos / letras:
    1. yfinance (primary)
    2. Stooq via pandas_datareader (free, no auth, US stocks/ETFs)

  crypto:
    1. yfinance (primary)  
    2. Binance REST API (free, no auth, very reliable)
    3. CoinGecko API (free, rate limited, last resort)

Todos retornan un DataFrame OHLCV con columnas:
  ['Open', 'High', 'Low', 'Close', 'Volume'] y DatetimeIndex timezone-naive.
"""

import asyncio
import time
import requests
import pandas as pd
import numpy as np

# ─── Mapas para Binance ──────────────────────────────────────────────────────
# yfinance usa "BTC-USD", Binance usa "BTCUSDT"
_CRYPTO_TO_BINANCE: dict[str, str] = {
    "BTC-USD":   "BTCUSDT",
    "ETH-USD":   "ETHUSDT",
    "BNB-USD":   "BNBUSDT",
    "SOL-USD":   "SOLUSDT",
    "XRP-USD":   "XRPUSDT",
    "ADA-USD":   "ADAUSDT",
    "DOGE-USD":  "DOGEUSDT",
    "AVAX-USD":  "AVAXUSDT",
    "LINK-USD":  "LINKUSDT",
    "DOT-USD":   "DOTUSDT",
    "MATIC-USD": "MATICUSDT",
    "LTC-USD":   "LTCUSDT",
    "TRX-USD":   "TRXUSDT",
    "ATOM-USD":  "ATOMUSDT",
    "UNI-USD":   "UNIUSDT",
    "NEAR-USD":  "NEARUSDT",
    "APT-USD":   "APTUSDT",
    "INJ-USD":   "INJUSDT",
    "ARB-USD":   "ARBUSDT",
    "OP-USD":    "OPUSDT",
    "SUI-USD":   "SUIUSDT",
    "SEI-USD":   "SEIUSDT",
    "WIF-USD":   "WIFUSDT",
    "JUP-USD":   "JUPUSDT",
}

# CoinGecko: mapa ticker yfinance → id coingecko
_CRYPTO_TO_COINGECKO: dict[str, str] = {
    "BTC-USD":   "bitcoin",
    "ETH-USD":   "ethereum",
    "BNB-USD":   "binancecoin",
    "SOL-USD":   "solana",
    "XRP-USD":   "ripple",
    "ADA-USD":   "cardano",
    "DOGE-USD":  "dogecoin",
    "AVAX-USD":  "avalanche-2",
    "LINK-USD":  "chainlink",
    "DOT-USD":   "polkadot",
    "MATIC-USD": "matic-network",
    "LTC-USD":   "litecoin",
    "TRX-USD":   "tron",
    "ATOM-USD":  "cosmos",
    "UNI-USD":   "uniswap",
    "NEAR-USD":  "near",
    "APT-USD":   "aptos",
    "INJ-USD":   "injective-protocol",
    "ARB-USD":   "arbitrum",
    "OP-USD":    "optimism",
    "SUI-USD":   "sui",
}

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "PicadoFino/1.0 contact@picadofino.com"


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Estandariza columnas y elimina timezone del índice."""
    # Normalizar nombres de columnas
    col_map = {}
    for c in df.columns:
        lc = c.lower()
        if lc in ("open", "o"):   col_map[c] = "Open"
        elif lc in ("high", "h"): col_map[c] = "High"
        elif lc in ("low", "l"):  col_map[c] = "Low"
        elif lc in ("close", "c", "adj close"): col_map[c] = "Close"
        elif lc in ("volume", "v"): col_map[c] = "Volume"
    df = df.rename(columns=col_map)
    # Mantener solo columnas requeridas
    for col in ("Open", "High", "Low", "Close"):
        if col not in df.columns:
            df[col] = np.nan
    if "Volume" not in df.columns:
        df["Volume"] = 0
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    # Normalizar índice
    if hasattr(df.index, "tz") and df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    df = df.dropna(subset=["Close"])
    return df


# ─── Providers individuales ──────────────────────────────────────────────────

def _fetch_yfinance(ticker: str, period_days: int = 365) -> pd.DataFrame | None:
    """Descarga datos de Yahoo Finance para un solo ticker con timeout corto."""
    try:
        import yfinance as yf
        # Crear sesión con User-Agent moderno para evitar bloqueos
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        t = yf.Ticker(ticker, session=s)
        df = t.history(period=f"{period_days}d", interval="1d", timeout=8, raise_errors=False)
        if df is None or df.empty:
            return None
        return _normalize_df(df)
    except Exception as e:
        print(f"[yfinance] {ticker}: {e}")
        return None


def _fetch_binance(ticker: str, days: int = 365) -> pd.DataFrame | None:
    """Descarga klines diarios de Binance. Solo para crypto (sin auth)."""
    binance_sym = _CRYPTO_TO_BINANCE.get(ticker)
    if not binance_sym:
        return None
    try:
        limit = min(days, 1000)
        url = "https://api.binance.com/api/v3/klines"
        resp = SESSION.get(url, params={
            "symbol": binance_sym,
            "interval": "1d",
            "limit": limit,
        }, timeout=8)
        resp.raise_for_status()
        raw = resp.json()
        if not raw:
            return None
        rows = []
        for k in raw:
            rows.append({
                "Open":   float(k[1]),
                "High":   float(k[2]),
                "Low":    float(k[3]),
                "Close":  float(k[4]),
                "Volume": float(k[5]),
            })
        index = pd.to_datetime([k[0] for k in raw], unit="ms")
        df = pd.DataFrame(rows, index=index)
        return _normalize_df(df)
    except Exception as e:
        print(f"[binance] {ticker}: {e}")
        return None


def _fetch_coingecko(ticker: str, days: int = 365) -> pd.DataFrame | None:
    """Descarga datos OHLCV de CoinGecko. Solo para crypto (sin auth, rate limited)."""
    cg_id = _CRYPTO_TO_COINGECKO.get(ticker)
    if not cg_id:
        return None
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/ohlc"
        resp = SESSION.get(url, params={"vs_currency": "usd", "days": days}, timeout=10)
        if resp.status_code == 429:
            print(f"[coingecko] Rate limited for {ticker}")
            return None
        resp.raise_for_status()
        raw = resp.json()
        if not raw:
            return None
        rows = []
        for entry in raw:
            rows.append({
                "Open": entry[1], "High": entry[2], "Low": entry[3], "Close": entry[4],
                "Volume": 0,  # CoinGecko OHLC no incluye volume en este endpoint
            })
        index = pd.to_datetime([e[0] for e in raw], unit="ms")
        df = pd.DataFrame(rows, index=index)
        return _normalize_df(df)
    except Exception as e:
        print(f"[coingecko] {ticker}: {e}")
        return None


# ─── Interfaz principal ──────────────────────────────────────────────────────

def fetch_ohlcv_single(ticker: str, category: str, days: int = 365) -> pd.DataFrame | None:
    """
    Descarga OHLCV para un ticker usando la cadena de fuentes adecuada para su categoría.

    Cadena para acciones (sp500, cedears, merval, bonos, letras):
        yfinance (única fuente pública keyless para acciones locales/CEDEARs)

    Cadena para crypto:
        yfinance → Binance → CoinGecko
    """
    if category == "crypto":
        sources = [
            ("yfinance", lambda: _fetch_yfinance(ticker, days)),
            ("binance",  lambda: _fetch_binance(ticker, days)),
            ("coingecko",lambda: _fetch_coingecko(ticker, days)),
        ]
    else:
        sources = [
            ("yfinance", lambda: _fetch_yfinance(ticker, days)),
        ]

    for source_name, fetch_fn in sources:
        df = fetch_fn()
        if df is not None and not df.empty and len(df) >= 30:
            if source_name != "yfinance":
                print(f"[data_providers] {ticker}: usando {source_name} como fuente.")
            return df

    print(f"[data_providers] {ticker}: sin datos en ninguna fuente.")
    return None


async def fetch_ohlcv_single_async(ticker: str, category: str, days: int = 365) -> tuple[str, pd.DataFrame | None]:
    """Versión async de fetch_ohlcv_single para descarga concurrente."""
    df = await asyncio.to_thread(fetch_ohlcv_single, ticker, category, days)
    return ticker, df


async def fetch_ohlcv_batch(
    tickers: list[str],
    categories: dict[str, str],
    days: int = 365,
    max_concurrent: int = 8,
) -> dict[str, pd.DataFrame]:
    """
    Descarga OHLCV para múltiples tickers en paralelo (limitado a max_concurrent).
    Retorna {ticker: DataFrame} con los datos obtenidos (excluye los que fallaron).
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _bounded_fetch(ticker: str) -> tuple[str, pd.DataFrame | None]:
        async with semaphore:
            return await fetch_ohlcv_single_async(ticker, categories.get(ticker, "sp500"), days)

    tasks = [_bounded_fetch(t) for t in tickers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    output: dict[str, pd.DataFrame] = {}
    for res in results:
        if isinstance(res, Exception):
            continue
        ticker, df = res
        if df is not None:
            output[ticker] = df
    return output
