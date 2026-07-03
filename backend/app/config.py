import os

PORT = int(os.getenv("PORT", 8000))
HOST = os.getenv("HOST", "0.0.0.0")

# Directorio de caché local para evitar llamadas excesivas a APIs externas
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.abspath(os.path.join(BASE_DIR, "../cache"))
os.makedirs(CACHE_DIR, exist_ok=True)
