"""
Servicio de Watchlist y Alertas Técnicas Personalizadas.
Permite al usuario definir activos favoritos con umbrales de alerta
en indicadores técnicos (RSI, Volatilidad, Precio).
"""
import os
import json
import time
from app.config import CACHE_DIR

WATCHLIST_FILE = os.path.join(CACHE_DIR, "watchlist.json")


def _load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"items": []}


def _save_watchlist(data):
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_watchlist():
    return _load_watchlist().get("items", [])


def add_to_watchlist(ticker, name, category, alert_rules=None):
    """
    Agrega un activo a la watchlist con reglas de alerta opcionales.
    
    alert_rules ejemplo:
    {
        "rsi_below": 30,
        "rsi_above": 70,
        "price_below": 100.0,
        "price_above": 200.0,
        "volatility_above": 0.40
    }
    """
    watchlist = _load_watchlist()
    
    # Evitar duplicados
    existing = [w for w in watchlist["items"] if w["ticker"] == ticker]
    if existing:
        # Actualizar reglas
        for item in watchlist["items"]:
            if item["ticker"] == ticker:
                item["alert_rules"] = alert_rules or {}
                item["updated_at"] = time.time()
        _save_watchlist(watchlist)
        return existing[0]
    
    item = {
        "ticker": ticker,
        "name": name,
        "category": category,
        "alert_rules": alert_rules or {},
        "added_at": time.time(),
        "updated_at": time.time()
    }
    watchlist["items"].append(item)
    _save_watchlist(watchlist)
    return item


def remove_from_watchlist(ticker):
    watchlist = _load_watchlist()
    watchlist["items"] = [w for w in watchlist["items"] if w["ticker"] != ticker]
    _save_watchlist(watchlist)
    return True


def check_alerts(watchlist_items, market_data):
    """
    Evalúa las reglas de alerta contra datos de mercado actuales.
    Retorna una lista de alertas disparadas.
    """
    alerts = []
    
    # Construir lookup rápido
    price_map = {}
    for asset in market_data:
        price_map[asset["ticker"]] = asset
    
    for item in watchlist_items:
        ticker = item["ticker"]
        rules = item.get("alert_rules", {})
        asset_data = price_map.get(ticker)
        
        if not asset_data or not rules:
            continue
        
        rsi = asset_data.get("rsi", 50)
        price = asset_data.get("price", 0)
        vol = asset_data.get("volatility", 0.20)
        
        # Evaluar cada regla
        if "rsi_below" in rules and rsi < rules["rsi_below"]:
            alerts.append({
                "ticker": ticker,
                "name": item["name"],
                "type": "RSI Sobreventa",
                "icon": "fa-arrow-down",
                "color": "warning",
                "message": f"RSI en {rsi:.1f} (umbral: {rules['rsi_below']}). Posible zona de oportunidad.",
                "current_value": rsi,
                "threshold": rules["rsi_below"]
            })
        
        if "rsi_above" in rules and rsi > rules["rsi_above"]:
            alerts.append({
                "ticker": ticker,
                "name": item["name"],
                "type": "RSI Sobrecompra",
                "icon": "fa-arrow-up",
                "color": "danger",
                "message": f"RSI en {rsi:.1f} (umbral: {rules['rsi_above']}). Considerar toma de ganancias.",
                "current_value": rsi,
                "threshold": rules["rsi_above"]
            })
        
        if "price_below" in rules and price < rules["price_below"]:
            alerts.append({
                "ticker": ticker,
                "name": item["name"],
                "type": "Precio Bajo Umbral",
                "icon": "fa-tag",
                "color": "success",
                "message": f"Precio actual {price:.2f} cayó por debajo de {rules['price_below']:.2f}.",
                "current_value": price,
                "threshold": rules["price_below"]
            })
        
        if "price_above" in rules and price > rules["price_above"]:
            alerts.append({
                "ticker": ticker,
                "name": item["name"],
                "type": "Precio Sobre Umbral",
                "icon": "fa-rocket",
                "color": "success",
                "message": f"Precio actual {price:.2f} superó el objetivo de {rules['price_above']:.2f}.",
                "current_value": price,
                "threshold": rules["price_above"]
            })
        
        if "volatility_above" in rules and vol > rules["volatility_above"]:
            alerts.append({
                "ticker": ticker,
                "name": item["name"],
                "type": "Alta Volatilidad",
                "icon": "fa-wave-square",
                "color": "warning",
                "message": f"Volatilidad en {vol*100:.1f}% (umbral: {rules['volatility_above']*100:.1f}%).",
                "current_value": vol,
                "threshold": rules["volatility_above"]
            })
    
    return alerts
