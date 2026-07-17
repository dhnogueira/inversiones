"""
market_screener.py — Interfaz pública del sistema de screening.

Delega toda la lógica al motor de funnel en cascada (asset_funnel.py).
Mantiene la misma interfaz de salida que consumía el frontend originalmente,
ahora con soporte completo de perfil e horizonte.

El resultado incluye por categoría los activos que superaron
los 3 filtros del funnel, ordenados por funnel_score descendente.
"""
import os
import json
import time

from app.services.asset_funnel import run_funnel, run_funnel_all_profiles


async def run_market_screener(
    profile: str = "moderado",
    horizon: str = "medium",
    force_refresh: bool = False,
) -> dict:
    """
    Ejecuta el funnel de selección en cascada para el perfil y horizonte
    indicados y retorna el resultado en el formato esperado por el frontend.

    Args:
        profile:  "conservador" | "moderado" | "agresivo"
        horizon:  "short" | "medium" | "long"
        force_refresh: si True, ignora la caché y recalcula.

    Returns:
        {
          "pipeline": { ... métricas del funnel ... },
          "results":  {
              "sp500":   [ { ticker, funnel_score, ... métricas completas } ],
              "cedears": [ ... ],
              "merval":  [ ... ],
              "crypto":  [ ... ],
          }
        }
    """
    return await run_funnel(profile=profile, horizon=horizon, force_refresh=force_refresh)


async def run_screener_all_profiles(force_refresh: bool = False) -> dict:
    """
    Ejecuta el screener para los 9 combos perfil×horizonte.
    Usado por el scheduler diario.
    """
    return await run_funnel_all_profiles()
