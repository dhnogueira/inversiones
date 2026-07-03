"""
Servicio de Cartera Simulada.
Permite agregar, listar y eliminar posiciones simuladas con tracking de P&L.
Los datos se persisten en un archivo JSON local.
"""
import os
import json
import time
import uuid
from app.config import CACHE_DIR

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


def get_all_positions():
    """Retorna todas las posiciones de la cartera simulada."""
    return _load_portfolio().get("positions", [])


def add_position(ticker, name, category, currency, entry_price, quantity):
    """Agrega una nueva posición simulada a la cartera."""
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


def remove_position(position_id):
    """Elimina una posición por su ID."""
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
