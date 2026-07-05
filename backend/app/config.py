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
