import os
import json
import asyncio
import sys

# Añadir directorio actual al path para importar módulos correctamente
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.yfinance_service import fetch_yfinance_market_data
from app.services.arg_fixed_income import fetch_arg_fixed_income_data
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
    
    # 2. Descargar y combinar datos reales de mercado
    print("Recuperando cotizaciones de mercado y de renta fija...")
    yf_assets = await fetch_yfinance_market_data(force_refresh=True)
    fi_assets = await fetch_arg_fixed_income_data(force_refresh=True)
    all_assets = yf_assets + fi_assets
    
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
            rec_data = {"status": "success", "updating": False, "results": scored}
            with open(os.path.join(API_DIR, "recommendations", f"{profile}-{horizon}.json"), "w", encoding="utf-8") as f:
                json.dump(rec_data, f, indent=2, ensure_ascii=False)
                
            # Compatibility fallback: write to profile.json (medium)
            if horizon == "medium":
                with open(os.path.join(API_DIR, "recommendations", f"{profile}.json"), "w", encoding="utf-8") as f:
                    json.dump(rec_data, f, indent=2, ensure_ascii=False)
                
            # Markowitz efficient allocation optimization
            top_assets = scored["top_10"]
            optimal = optimize_portfolio(top_assets, profile, horizon)
            opt_data = {"status": "success", "optimization": optimal}
            with open(os.path.join(API_DIR, "optimize", f"{profile}-{horizon}.json"), "w", encoding="utf-8") as f:
                json.dump(opt_data, f, indent=2, ensure_ascii=False)
                
            if horizon == "medium":
                with open(os.path.join(API_DIR, "optimize", f"{profile}.json"), "w", encoding="utf-8") as f:
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

    # 5. Generar historial de alertas estático (copiando desde el cache)
    print("Compilando historial de alertas enviado...")
    import shutil
    cache_history = os.path.join(os.path.dirname(__file__), "cache", "alert_history.json")
    api_history = os.path.join(API_DIR, "alert-history.json")
    if os.path.exists(cache_history):
        shutil.copy(cache_history, api_history)
        print("✓ Historial de alertas compilado correctamente.")
    else:
        with open(api_history, "w", encoding="utf-8") as f:
            json.dump([], f)
        print("✓ Historial de alertas vacío creado.")

    print("Compilación estática completada con éxito. Todos los archivos JSON generados en frontend/api/")


if __name__ == "__main__":
    asyncio.run(main())

