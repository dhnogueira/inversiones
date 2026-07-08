import os

# Cargar .env manualmente si existe
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.abspath(os.path.join(BASE_DIR, "../.env"))
if os.path.exists(ENV_FILE):
    with open(ENV_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

PORT = int(os.getenv("PORT", 8000))
HOST = os.getenv("HOST", "0.0.0.0")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")

# ===== SMTP / Email Config =====
ALERT_EMAIL_FROM = os.getenv("ALERT_EMAIL_FROM", "")
ALERT_EMAIL_PASSWORD = os.getenv("ALERT_EMAIL_PASSWORD", "")
ALERT_EMAIL_SMTP_HOST = os.getenv("ALERT_EMAIL_SMTP_HOST", "smtp.gmail.com")
ALERT_EMAIL_SMTP_PORT = os.getenv("ALERT_EMAIL_SMTP_PORT", "587")
SITE_URL = os.getenv("SITE_URL", "https://dhnogueira.github.io/inversiones")

# Directorio de caché local para evitar llamadas excesivas a APIs externas
CACHE_DIR = os.path.abspath(os.path.join(BASE_DIR, "../cache"))
os.makedirs(CACHE_DIR, exist_ok=True)

import json
def register_custom_ticker(ticker: str):
    """Guarda un ticker de forma persistente en cache/custom_tickers.json si no es de las listas por defecto."""
    if not ticker:
        return
    ticker = ticker.upper().strip()
    # Listas por defecto para no redundar
    default_tickers = {
        "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "BRK-B", "LLY", "AVGO", "JPM", "TSLA", "XOM", "UNH", "PG", "V", "MA", "HD", "COST", "MRK", "ABBV",
        "AAPL.BA", "MSFT.BA", "TSLA.BA", "MELI.BA", "KO.BA", "NVDA.BA", "AMZN.BA", "META.BA", "GOOGL.BA", "XOM.BA", "BABA.BA", "VALE.BA", "PBR.BA", "GGLD.BA", "DESP.BA",
        "YPFD.BA", "GGAL.BA", "PAMP.BA", "ALUA.BA", "TXAR.BA", "BMA.BA", "CEPU.BA", "TGSU2.BA", "EDN.BA", "LOMA.BA", "CRES.BA", "TECO2.BA", "SUPV.BA", "VALO.BA", "BYMA.BA",
        "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD", "AVAX-USD", "LINK-USD", "DOT-USD",
        "AL30.BA", "GD30.BA", "AL29.BA", "GD29.BA", "AL35.BA", "GD35.BA", "AE38.BA", "GD38.BA", "AL41.BA", "GD41.BA"
    }
    if ticker in default_tickers:
        return
    
    file_path = os.path.join(CACHE_DIR, "custom_tickers.json")
    custom_tickers = []
    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                custom_tickers = json.load(f)
        except Exception:
            pass
    if not isinstance(custom_tickers, list):
        custom_tickers = []
    if ticker not in custom_tickers:
        custom_tickers.append(ticker)
        try:
            with open(file_path, "w") as f:
                json.dump(custom_tickers, f, indent=2)
            print(f"[config] Ticker manual registrado con éxito: {ticker}")
        except Exception as e:
            print(f"[config] Error registrando ticker manual {ticker}: {e}")
