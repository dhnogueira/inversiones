"""
Servicio de Cartera Simulada.
Permite agregar, listar y eliminar posiciones simuladas con tracking de P&L.
Los datos se persisten en un archivo JSON local.
"""
import os
import json
import time
import uuid
import httpx
from app.config import CACHE_DIR, SUPABASE_URL, SUPABASE_ANON_KEY, register_custom_ticker

PORTFOLIO_FILE = os.path.join(CACHE_DIR, "portfolio.json")


def _load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"positions": [], "created_at": time.time()}


def _save_portfolio(data):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(data, f, indent=2)


async def get_all_positions(user: dict = None):
    """Retorna todas las posiciones de la cartera simulada, o de Supabase si el usuario está autenticado."""
    print(f"[DIAGNOSTIC] get_all_positions called. user={user}")
    if user and SUPABASE_URL and SUPABASE_ANON_KEY:
        # Cargar desde Supabase
        base_url = SUPABASE_URL.rstrip("/").replace("/rest/v1", "")
        url = f"{base_url}/rest/v1/portfolios?select=*"
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {user['token']}",
            "Content-Type": "application/json"
        }
        print(f"[DIAGNOSTIC] Contacting Supabase at {url} with user token.")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers)
                print(f"[DIAGNOSTIC] Supabase portfolios GET response status_code={response.status_code}")
                if response.status_code == 200:
                    positions = response.json()
                    print(f"[DIAGNOSTIC] Supabase portfolios returned {len(positions)} records.")
                    mapped = []
                    for p in positions:
                        # Auto-register manual tickers
                        register_custom_ticker(p["ticker"])
                        mapped.append({
                            "id": p["id"],
                            "ticker": p["ticker"],
                            "name": p["name"],
                            "category": p["category"],
                            "currency": p["currency"],
                            "entry_price": float(p["entry_price"]),
                            "quantity": float(p["quantity"]),
                            "entry_date": p["entry_date"]
                        })
                    return mapped
                  
                else:
                    print(f"[DIAGNOSTIC] Error querying Supabase portfolios: {response.text}")
        except Exception as e:
            print(f"[DIAGNOSTIC] Exception querying Supabase: {e}")
 
    print("[DIAGNOSTIC] Falling back to local portfolio storage.")
    # Fallback local
    local_pos = _load_portfolio().get("positions", [])
    for p in local_pos:
        register_custom_ticker(p["ticker"])
    return local_pos


async def add_position(ticker, name, category, currency, entry_price, quantity, user: dict = None):
    """Agrega una nueva posición simulada a la cartera (Local o Supabase)."""
    register_custom_ticker(ticker)
    if user and SUPABASE_URL and SUPABASE_ANON_KEY:
        base_url = SUPABASE_URL.rstrip("/").replace("/rest/v1", "")
        url = f"{base_url}/rest/v1/portfolios"
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {user['token']}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        payload = {
            "user_id": user["id"],
            "ticker": ticker,
            "name": name,
            "category": category,
            "currency": currency,
            "entry_price": float(entry_price),
            "quantity": float(quantity)
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code == 201:
                    data = response.json()
                    if data:
                        p = data[0]
                        return {
                            "id": p["id"],
                            "ticker": p["ticker"],
                            "name": p["name"],
                            "category": p["category"],
                            "currency": p["currency"],
                            "entry_price": float(p["entry_price"]),
                            "quantity": float(p["quantity"]),
                            "entry_date": p["entry_date"]
                        }
                print(f"Error saving to Supabase: {response.text}")
        except Exception as e:
            print(f"Exception saving to Supabase: {e}")

    # Fallback local
    portfolio = _load_portfolio()
    position = {
        "id": str(uuid.uuid4())[:8],
        "ticker": ticker,
        "name": name,
        "category": category,
        "currency": currency,
        "entry_price": float(entry_price),
        "quantity": float(quantity),
        "entry_date": time.strftime("%Y-%m-%d"),
        "timestamp": time.time()
    }
    portfolio["positions"].append(position)
    _save_portfolio(portfolio)
    return position


async def remove_position(position_id, user: dict = None):
    """Elimina una posición por su ID (Local o Supabase)."""
    if user and SUPABASE_URL and SUPABASE_ANON_KEY:
        base_url = SUPABASE_URL.rstrip("/").replace("/rest/v1", "")
        url = f"{base_url}/rest/v1/portfolios?id=eq.{position_id}"
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {user['token']}",
            "Content-Type": "application/json"
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(url, headers=headers)
                if response.status_code in (200, 204):
                    return True
                print(f"Error deleting from Supabase: {response.text}")
        except Exception as e:
            print(f"Exception deleting from Supabase: {e}")

    # Fallback local
    portfolio = _load_portfolio()
    portfolio["positions"] = [p for p in portfolio["positions"] if p["id"] != position_id]
    _save_portfolio(portfolio)
    return True


def calculate_portfolio_pnl(positions, current_prices):
    """
    Calcula el P&L de cada posición comparando precio de entrada vs. precio actual.
    
    Args:
        positions: Lista de posiciones guardadas
        current_prices: Dict {ticker: current_price}
    
    Returns:
        Lista de posiciones enriquecidas con P&L
    """
    enriched = []
    total_invested = 0
    total_current = 0

    for pos in positions:
        current = current_prices.get(pos["ticker"], pos["entry_price"])
        invested = pos["entry_price"] * pos["quantity"]
        current_value = current * pos["quantity"]
        pnl = current_value - invested
        pnl_pct = (pnl / invested * 100) if invested > 0 else 0

        total_invested += invested
        total_current += current_value

        enriched.append({
            **pos,
            "current_price": round(current, 2),
            "invested": round(invested, 2),
            "current_value": round(current_value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2)
        })

    total_pnl = total_current - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0

    return {
        "positions": enriched,
        "summary": {
            "total_invested": round(total_invested, 2),
            "total_current": round(total_current, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "count": len(enriched)
        }
    }
