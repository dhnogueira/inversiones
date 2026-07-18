import os
import json
import asyncio
import sys

# Añadir directorio actual al path para importar módulos correctamente
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.yfinance_service import fetch_yfinance_market_data
from app.services.arg_fixed_income import fetch_arg_fixed_income_data
from app.services.market_screener import run_market_screener
from app.scoring.profiles import get_recommendations_by_profile, score_asset_for_profile
from app.scoring.analysis import generate_asset_analysis
from app.scoring.optimizer import optimize_portfolio

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend"))
API_DIR = os.path.join(FRONTEND_DIR, "api")


def ensure_directory(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


async def main():
    print("Iniciando compilador de sitio estático (Build Pipeline)...")
    
    # 1. Asegurar directorios de la API estática
    ensure_directory(API_DIR)
    ensure_directory(os.path.join(API_DIR, "recommendations"))
    ensure_directory(os.path.join(API_DIR, "optimize"))
    
    # 2. Leer datos desde caché en disco (el scheduler de 10 min los mantiene frescos).
    # use_cache_only=True: sin TTL, sin descarga — evita rate-limiting de Yahoo Finance en subprocess.
    print("Recuperando cotizaciones de mercado y de renta fija desde caché (sin descarga)...")
    yf_assets = await fetch_yfinance_market_data(use_cache_only=True)
    fi_assets = await fetch_arg_fixed_income_data(force_refresh=False)
    all_assets = yf_assets + fi_assets

    # Obtener el timestamp exacto de la última actualización del mercado desde el caché de yfinance
    cache_path = os.path.join(os.path.dirname(__file__), "cache", "yfinance_market_data.json")
    market_data_time = None
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                c_data = json.load(f)
                market_data_time = c_data.get("timestamp")
        except Exception as e:
            print(f"Error al leer timestamp del cache de yfinance: {e}")
    if not market_data_time:
        import time
        market_data_time = time.time()
    
    # Validar que ningún instrumento de renta fija esté vencido (Seguridad en compilación)
    from datetime import datetime
    today_str = datetime.now().strftime("%Y-%m-%d")
    for asset in fi_assets:
        mat = asset.get("maturity")
        if mat and mat < today_str:
            raise ValueError(f"CRITICAL ERROR: El instrumento de renta fija '{asset['ticker']}' está vencido ({mat} < {today_str})! Se aborta la compilación estática.")
    
    # 3. Generar Yield Curve
    print("Generando datos de curva de rendimientos (Renta Fija)...")
    letras = [a for a in fi_assets if a["category"] == "letras"]
    bonos = [a for a in fi_assets if a["category"] == "bonos"]
    
    def _to_point(asset):
        from datetime import datetime
        mat = asset.get("maturity", "2025-12-31")
        try:
            days = (datetime.strptime(mat, "%Y-%m-%d") - datetime.now()).days
        except:
            days = 180
        return {
            "ticker": asset["ticker"],
            "name": asset["name"],
            "tna_pct": round(asset.get("tna", 0) * 100, 2),
            "maturity": mat,
            "days_to_maturity": max(days, 1),
            "currency": asset.get("currency", "ARS"),
            "price": asset.get("price", 0)
        }
    
    yield_curve_data = {
        "status": "success",
        "letras": [_to_point(l) for l in letras],
        "bonos": [_to_point(b) for b in bonos]
    }
    with open(os.path.join(API_DIR, "yield-curve.json"), "w", encoding="utf-8") as f:
        json.dump(yield_curve_data, f, indent=2, ensure_ascii=False)

    # 4. Generar reportes por cada perfil de riesgo y horizonte temporal
    profiles = ["conservador", "moderado", "agresivo"]
    horizons = ["short", "medium", "long"]
    
    for profile in profiles:
        for horizon in horizons:
            print(f"Generando recomendaciones y optimizaciones para perfil '{profile}' ({horizon})...")
            
            # Recommendations
            scored = get_recommendations_by_profile(all_assets, profile, horizon)
            rec_data = {
                "status": "success",
                "updating": False,
                "timestamp": market_data_time,
                "results": scored
            }
            with open(os.path.join(API_DIR, "recommendations", f"{profile}-{horizon}.json"), "w", encoding="utf-8") as f:
                json.dump(rec_data, f, indent=2, ensure_ascii=False)
                
            # Compatibility fallback: write to profile.json (medium)
            if horizon == "medium":
                with open(os.path.join(API_DIR, "recommendations", f"{profile}.json"), "w", encoding="utf-8") as f:
                    json.dump(rec_data, f, indent=2, ensure_ascii=False)
                
            # Markowitz efficient allocation optimization
            categories = ["all", "letras", "bonos", "merval", "cedears", "sp500", "crypto"]
            for cat in categories:
                if cat == "all":
                    top_assets = scored["top_10"]
                else:
                    top_assets = scored["categories"].get(cat, [])
                
                optimal = optimize_portfolio(top_assets, profile, horizon)
                opt_data = {
                    "status": "success",
                    "timestamp": market_data_time,
                    "optimization": optimal
                }
                
                # Guardar el específico por categoría: {profile}-{horizon}-{category}.json
                with open(os.path.join(API_DIR, "optimize", f"{profile}-{horizon}-{cat}.json"), "w", encoding="utf-8") as f:
                    json.dump(opt_data, f, indent=2, ensure_ascii=False)
                
                if cat == "all":
                    with open(os.path.join(API_DIR, "optimize", f"{profile}-{horizon}.json"), "w", encoding="utf-8") as f:
                        json.dump(opt_data, f, indent=2, ensure_ascii=False)
                    
                    if horizon == "medium":
                        with open(os.path.join(API_DIR, "optimize", f"{profile}.json"), "w", encoding="utf-8") as f:
                            json.dump(opt_data, f, indent=2, ensure_ascii=False)
                
                if horizon == "medium":
                    with open(os.path.join(API_DIR, "optimize", f"{profile}-{cat}.json"), "w", encoding="utf-8") as f:
                        json.dump(opt_data, f, indent=2, ensure_ascii=False)
                
            # Asset Modals Analysis
            print(f"Precalculando reportes narrativos detallados para perfil '{profile}' ({horizon})...")
            ensure_directory(os.path.join(API_DIR, "asset-analysis", f"{profile}-{horizon}"))
            if horizon == "medium":
                ensure_directory(os.path.join(API_DIR, "asset-analysis", profile))
            
            # Generar análisis para todos los activos
            for asset in all_assets:
                # Calcular score específico para este activo en este perfil e higiene de horizonte
                s = score_asset_for_profile(asset, profile, horizon)
                target = {**asset, "score": round(s, 1)}
                
                # Generar el reporte estructurado
                analysis = generate_asset_analysis(target, profile, horizon)
                analysis_data = {"status": "success", "analysis": analysis}
                
                # Prevenir problemas con caracteres especiales o encoding en nombres de archivo
                safe_ticker = asset["ticker"].replace("/", "_")
                
                filepath = os.path.join(API_DIR, "asset-analysis", f"{profile}-{horizon}", f"{safe_ticker}.json")
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(analysis_data, f, indent=2, ensure_ascii=False)
                    
                if horizon == "medium":
                    filepath_fallback = os.path.join(API_DIR, "asset-analysis", profile, f"{safe_ticker}.json")
                    with open(filepath_fallback, "w", encoding="utf-8") as f:
                        json.dump(analysis_data, f, indent=2, ensure_ascii=False)

    # 5. Generar tickers-data.json con todos los activos
    print("Generando lista unificada de precios y métricas de mercado...")
    tickers_dict = {}
    for asset in all_assets:
        tickers_dict[asset["ticker"]] = {
            "ticker": asset["ticker"],
            "name": asset.get("name", asset["ticker"]),
            "price": asset.get("price", 0.0),
            "category": asset.get("category", ""),
            "currency": asset.get("currency", "ARS"),
            "rsi": asset.get("rsi", 50.0),
            "sharpe": asset.get("sharpe", 0.5),
            "volatility": asset.get("volatility", 0.25),
            "trend": asset.get("trend", "Estable"),
            "ret_1m": asset.get("ret_1m", 0.0)
        }
    tickers_data = {"status": "success", "tickers": tickers_dict}
    with open(os.path.join(API_DIR, "tickers-data.json"), "w", encoding="utf-8") as f:
        json.dump(tickers_data, f, indent=2, ensure_ascii=False)
    print("[OK] Lista unificada tickers-data.json compilada correctamente.")

    # 6. Generar historial de alertas estático (copiando desde el cache)
    print("Compilando historial de alertas enviado...")
    import shutil
    cache_history = os.path.join(os.path.dirname(__file__), "cache", "alert_history.json")
    api_history = os.path.join(API_DIR, "alert-history.json")
    if os.path.exists(cache_history):
        shutil.copy(cache_history, api_history)
        print("[OK] Historial de alertas compilado correctamente.")
    else:
        with open(api_history, "w", encoding="utf-8") as f:
            json.dump([], f)
        print("[OK] Historial de alertas vacio creado.")

    # 7. Ejecutar el Market Screener de Joyas Ocultas para todos los combos perfil-horizonte
    print("Ejecutando Market Screener (Funnel en cascada) para todos los profiles/horizontes...")
    try:
        from app.services.market_screener import run_screener_all_profiles
        all_combos = await run_screener_all_profiles()
        
        total_new_global = 0
        for key, value in all_combos.items():
            p, h = key.split("_")
            results = value.get("results", {})
            pipeline = value.get("pipeline", {})
            total_count = sum(len(lst) for lst in results.values())
            
            screener_data = {
                "status": "success",
                "scan_date": datetime.now().strftime("%Y-%m-%d"),
                "total_new_discoveries": total_count,
                "categories": results,
                "pipeline": pipeline
            }
            
            filepath = os.path.join(API_DIR, f"market-screener-{p}-{h}.json")
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(screener_data, f, indent=2, ensure_ascii=False)
                
            if p == "moderado" and h == "medium":
                total_new_global = total_count
                fallback_path = os.path.join(API_DIR, "market-screener.json")
                with open(fallback_path, "w", encoding="utf-8") as f:
                    json.dump(screener_data, f, indent=2, ensure_ascii=False)
                    
        print(f"[OK] Market Screener completado. Oportunidades en moderado/medium: {total_new_global}.")
    except Exception as e:
        print(f"[WARNING] Market Screener falló (no crítico): {e}")
        # Generar un JSON vacío para que el frontend no falle
        with open(os.path.join(API_DIR, "market-screener.json"), "w", encoding="utf-8") as f:
            json.dump({"status": "error", "message": str(e), "categories": {}}, f)

    print("Compilación estática completada con éxito. Todos los archivos JSON generados en frontend/api/")


if __name__ == "__main__":
    asyncio.run(main())

