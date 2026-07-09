import asyncio
import os
import threading
from contextlib import asynccontextmanager
from typing import Optional, Dict
from fastapi import FastAPI, BackgroundTasks, Query, Body, Depends
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from app.services.yfinance_service import fetch_yfinance_market_data
from app.services.arg_fixed_income import fetch_arg_fixed_income_data
from app.scoring.profiles import get_recommendations_by_profile
from app.scoring.analysis import generate_asset_analysis
from app.scoring.optimizer import optimize_portfolio
from app.services.portfolio_service import (
    get_all_positions, add_position, remove_position, calculate_portfolio_pnl
)
from app.services.watchlist_service import (
    get_watchlist, add_to_watchlist, remove_from_watchlist, check_alerts
)
from app.services.auth_service import get_current_user

# Estado de carga de datos iniciales
is_updating = False

async def refresh_all_data(force=False):
    global is_updating
    if is_updating:
        print("Data update already in progress, skipping.")
        return
    is_updating = True
    try:
        print("Starting market data synchronous refresh...")
        await asyncio.gather(
            fetch_yfinance_market_data(force_refresh=force),
            fetch_arg_fixed_income_data(force_refresh=force)
        )
        print("Data refresh completed successfully.")
    except Exception as e:
        print(f"Error during market data refresh: {e}")
    finally:
        is_updating = False

def run_scheduler_refresh():
    import sys
    import subprocess
    
    # 1. Actualizar caché y base de datos locales
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(refresh_all_data(force=True))
    finally:
        loop.close()

    # Rutas base
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # Inversiones/backend
    root_dir = os.path.dirname(backend_dir) # Inversiones/

    # 2. Compilar los archivos estáticos en frontend/api
    try:
        python_executable = sys.executable or "python"
        build_script = os.path.join(backend_dir, "build_static.py")
        print(f"[scheduler] Ejecutando compilación estática: {python_executable} {build_script}")
        res_build = subprocess.run([python_executable, build_script], capture_output=True, text=True, cwd=backend_dir)
        if res_build.returncode == 0:
            print("[scheduler] Compilación estática finalizada con éxito.")
        else:
            print(f"[scheduler] Error compilando estáticos (código {res_build.returncode}): {res_build.stderr}")
    except Exception as e:
        print(f"[scheduler] Excepción al compilar estáticos: {e}")

    # 3. Autopush a GitHub Pages si se generaron cambios en frontend/api
    try:
        print(f"[scheduler] Ejecutando git add y verificación en {root_dir}")
        subprocess.run(["git", "add", "frontend/api/"], capture_output=True, text=True, cwd=root_dir)
        
        # Verificar cambios staged
        status_res = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=root_dir)
        staged_changes = [line for line in status_res.stdout.splitlines() if line.startswith(('M ', 'A ', 'D ', 'MM', 'AM'))]
        
        if staged_changes:
            print(f"[scheduler] Detectados {len(staged_changes)} cambios. Ejecutando git commit...")
            git_commit = subprocess.run(["git", "commit", "-m", "data: 10-minute automated market update"], capture_output=True, text=True, cwd=root_dir)
            print(f"[scheduler] Git commit ejecutado: {git_commit.stdout.strip()}")
        else:
            print("[scheduler] Sin cambios nuevos para commitear.")
    except Exception as e:
        print(f"[scheduler] Error en autopush: {e}")


scheduler = BackgroundScheduler()
# Ejecutar cada 10 minutos (interval)
scheduler.add_job(run_scheduler_refresh, 'interval', minutes=10, id='market_data_10_min')

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    asyncio.create_task(refresh_all_data(force=False))
    yield
    scheduler.shutdown()

app = FastAPI(
    title="Inversiones API", 
    description="Motor cuantitativo de recomendación de inversiones",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "../../frontend"))

# ===== STATIC FILES =====
@app.get("/")
def read_root():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

@app.get("/index.css")
def read_css():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.css"))

@app.get("/main.js")
def read_js():
    return FileResponse(os.path.join(FRONTEND_DIR, "main.js"))

@app.get("/config.js")
def read_config_js():
    return FileResponse(os.path.join(FRONTEND_DIR, "config.js"))

# ===== HEALTH =====
@app.get("/api/health")
def read_health():
    return {"status": "online", "updating": is_updating}

# ===== HELPER: load all assets =====
async def _get_all_assets():
    yf = await fetch_yfinance_market_data(force_refresh=False)
    fi = await fetch_arg_fixed_income_data(force_refresh=False)
    return yf + fi

# ===== RECOMMENDATIONS =====
@app.get("/api/recommendations")
async def get_recommendations(
    profile: str = Query("moderado", regex="^(conservador|moderado|agresivo)$"),
    horizon: str = Query("medium", regex="^(short|medium|long)$")
):
    all_assets = await _get_all_assets()
    results = get_recommendations_by_profile(all_assets, profile, horizon)
    return {"status": "success", "updating": is_updating, "results": results}

# ===== ASSET ANALYSIS (Modal) =====
@app.get("/api/asset-analysis")
async def get_asset_analysis(
    ticker: str = Query(...),
    profile: str = Query("moderado", regex="^(conservador|moderado|agresivo)$"),
    horizon: str = Query("medium", regex="^(short|medium|long)$")
):
    all_assets = await _get_all_assets()
    scored = get_recommendations_by_profile(all_assets, profile, horizon)
    target = None
    
    for a in scored.get("top_10", []):
        if a["ticker"] == ticker:
            target = a; break
    if not target:
        for cat_list in scored.get("categories", {}).values():
            for a in cat_list:
                if a["ticker"] == ticker:
                    target = a; break
            if target: break
    if not target:
        from app.scoring.profiles import score_asset_for_profile
        for a in all_assets:
            if a["ticker"] == ticker:
                s = score_asset_for_profile(a, profile, horizon)
                target = {**a, "score": round(s, 1)}; break
    
    if not target:
        # Dynamic fallback for custom tickers
        import yfinance as yf_lib
        import pandas as pd
        try:
            ticker_upper = ticker.upper().strip()
            df = yf_lib.download(ticker_upper, period="2y", interval="1d", group_by="ticker", progress=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df_clean = df[ticker_upper].dropna(subset=['Close'])
                else:
                    df_clean = df.dropna(subset=['Close'])
                
                if not df_clean.empty and len(df_clean) >= 50:
                    from app.services.yfinance_service import compute_asset_metrics, fetch_fundamental_metrics
                    category = "cedears" if ticker_upper.endswith(".BA") else "sp500"
                    metrics = compute_asset_metrics(df_clean, ticker_upper, category)
                    if metrics:
                        fundamentals = fetch_fundamental_metrics(ticker_upper, category)
                        metrics.update(fundamentals)
                        from app.config import register_custom_ticker
                        register_custom_ticker(ticker_upper)
                        from app.scoring.profiles import score_asset_for_profile
                        s = score_asset_for_profile(metrics, profile, horizon)
                        target = {**metrics, "score": round(s, 1)}
        except Exception as e:
            print(f"Error fetching dynamic analysis for custom ticker {ticker}: {e}")

    if not target:
        return {"status": "error", "message": f"Activo '{ticker}' no encontrado."}
    
    analysis = generate_asset_analysis(target, profile, horizon)
    return {"status": "success", "analysis": analysis}

# ===== PORTFOLIO OPTIMIZER (Markowitz) =====
@app.get("/api/optimize")
async def get_optimal_portfolio(
    profile: str = Query("moderado", regex="^(conservador|moderado|agresivo)$"),
    horizon: str = Query("medium", regex="^(short|medium|long)$"),
    category: str = Query("all")
):
    all_assets = await _get_all_assets()
    scored = get_recommendations_by_profile(all_assets, profile, horizon)
    
    if category == "all":
        top_assets = scored["top_10"]
    else:
        top_assets = scored["categories"].get(category, [])
        # Si la lista de la categoría está vacía en 'categories', intentar filtrar scored_assets completos
        if not top_assets:
            # Por si acaso la categoría está vacía por falta de activos calificados en el top
            pass

    result = optimize_portfolio(top_assets, profile, horizon)
    return {"status": "success", "optimization": result}

# ===== YIELD CURVE (Renta Fija) =====
@app.get("/api/yield-curve")
async def get_yield_curve():
    fi = await fetch_arg_fixed_income_data(force_refresh=False)
    letras = [a for a in fi if a["category"] == "letras"]
    bonos = [a for a in fi if a["category"] == "bonos"]
    
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
    
    return {
        "status": "success",
        "letras": [_to_point(l) for l in letras],
        "bonos": [_to_point(b) for b in bonos]
    }

# ===== TICKERS DATA (Unified list of prices and metrics) =====
@app.get("/api/tickers-data")
async def get_tickers_data_api():
    all_assets = await _get_all_assets()
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
    return {"status": "success", "tickers": tickers_dict}

# ===== PORTFOLIO (Mi Cartera) =====
@app.get("/api/portfolio")
async def get_portfolio(user: Optional[Dict] = Depends(get_current_user)):
    positions = await get_all_positions(user)
    all_assets = await _get_all_assets()
    price_map = {a["ticker"]: a["price"] for a in all_assets}
    
    # Dynamically fetch missing prices for custom tickers
    missing_tickers = [p["ticker"] for p in positions if p["ticker"] not in price_map]
    if missing_tickers:
        print(f"Dynamically fetching prices for missing custom tickers: {missing_tickers}")
        import yfinance as yf_lib
        try:
            tick_data = yf_lib.download(missing_tickers, period="5d", interval="1d", group_by="ticker", progress=False)
            for t in missing_tickers:
                try:
                    if len(missing_tickers) == 1:
                        df_t = tick_data.dropna(subset=['Close'])
                    else:
                        df_t = tick_data[t].dropna(subset=['Close'])
                    if not df_t.empty:
                        price_map[t] = float(df_t['Close'].iloc[-1])
                        print(f"Loaded price dynamically for {t}: {price_map[t]}")
                except Exception as ex:
                    print(f"Error parsing on-the-fly price for {t}: {ex}")
        except Exception as e:
            print(f"Error fetching on-the-fly prices for {missing_tickers}: {e}")
            
    result = calculate_portfolio_pnl(positions, price_map)
    return {"status": "success", **result}

@app.post("/api/portfolio")
async def post_portfolio(data: dict = Body(...), user: Optional[Dict] = Depends(get_current_user)):
    pos = await add_position(
        data["ticker"], data["name"], data["category"],
        data["currency"], data["entry_price"], data["quantity"],
        user=user
    )
    return {"status": "success", "position": pos}

@app.delete("/api/portfolio/{position_id}")
async def delete_portfolio(position_id: str, user: Optional[Dict] = Depends(get_current_user)):
    await remove_position(position_id, user=user)
    return {"status": "success"}

@app.get("/api/portfolio/report")
async def get_portfolio_report_endpoint(
    profile: str = Query("moderado", regex="^(conservador|moderado|agresivo)$"),
    horizon: str = Query("medium", regex="^(short|medium|long)$"),
    user: Optional[Dict] = Depends(get_current_user)
):
    from app.services.portfolio_report_service import generate_portfolio_report
    positions = await get_all_positions(user)
    all_assets = await _get_all_assets()
    price_map = {a["ticker"]: a["price"] for a in all_assets}
    
    # Dynamically fetch missing prices/assets for custom tickers and add to all_assets
    missing_tickers = [p["ticker"] for p in positions if p["ticker"] not in price_map]
    if missing_tickers:
        print(f"Dynamically fetching assets for missing custom tickers in report: {missing_tickers}")
        import yfinance as yf_lib
        import pandas as pd
        try:
            tick_data = yf_lib.download(missing_tickers, period="2y", interval="1d", group_by="ticker", progress=False)
            for t in missing_tickers:
                try:
                    if len(missing_tickers) == 1:
                        df_t = tick_data.dropna(subset=['Close'])
                    else:
                        df_t = tick_data[t].dropna(subset=['Close'])
                    if not df_t.empty and len(df_t) >= 50:
                        from app.services.yfinance_service import compute_asset_metrics, fetch_fundamental_metrics
                        category = "cedears" if t.endswith(".BA") else "sp500"
                        metrics = compute_asset_metrics(df_t, t, category)
                        if metrics:
                            fundamentals = fetch_fundamental_metrics(t, category)
                            metrics.update(fundamentals)
                            price_map[t] = metrics["price"]
                            all_assets.append(metrics)
                            print(f"Loaded asset metrics dynamically for report: {t}")
                except Exception as ex:
                    print(f"Error parsing on-the-fly asset for report {t}: {ex}")
        except Exception as e:
            print(f"Error fetching on-the-fly assets for report: {e}")
            
    pnl_data = calculate_portfolio_pnl(positions, price_map)
    report = generate_portfolio_report(pnl_data["positions"], all_assets, profile, horizon)
    return {"status": "success", "report": report}

# ===== WATCHLIST & ALERTS =====
@app.get("/api/watchlist")
async def get_watchlist_endpoint(user: Optional[Dict] = Depends(get_current_user)):
    items = await get_watchlist(user)
    all_assets = await _get_all_assets()
    alerts = check_alerts(items, all_assets)
    return {"status": "success", "watchlist": items, "alerts": alerts}

@app.post("/api/watchlist")
async def post_watchlist(data: dict = Body(...), user: Optional[Dict] = Depends(get_current_user)):
    item = await add_to_watchlist(
        data["ticker"], data["name"], data["category"],
        data.get("alert_rules", {}),
        user=user
    )
    return {"status": "success", "item": item}

@app.delete("/api/watchlist/{ticker}")
async def delete_watchlist(ticker: str, user: Optional[Dict] = Depends(get_current_user)):
    await remove_from_watchlist(ticker, user=user)
    return {"status": "success"}

# ===== EMAIL ALERTS & SUBSCRIPTIONS =====
@app.get("/api/alert-history")
async def get_alert_history_endpoint():
    from app.services.email_service import load_alert_history
    return load_alert_history()

@app.post("/api/subscribe")
async def post_subscribe(data: dict = Body(...)):
    email = data.get("email")
    if not email:
        return {"status": "error", "message": "Email es requerido."}
    from app.services.email_service import add_subscriber
    res = add_subscriber(email)
    return res

async def dispatch_daily_alert_email():
    """Genera las recomendaciones y despacha el correo con el Top 5 de cada categoría."""
    all_assets = await _get_all_assets()
    scored = get_recommendations_by_profile(all_assets, "moderado", "medium")
    
    categories_data = scored.get("categories", {})
    categorized_top5 = {}
    
    # Para cada categoría, ordenar por score descendente y tomar los top 5
    for cat_name, asset_list in categories_data.items():
        sorted_assets = sorted(asset_list, key=lambda x: x.get("score", 0), reverse=True)[:5]
        if sorted_assets:
            categorized_top5[cat_name] = sorted_assets

    if categorized_top5:
        from app.services.email_service import send_daily_alert_email
        send_daily_alert_email(categorized_top5)
        print("[scheduler] Alerta diaria enviada por email por categorías con éxito.")
    else:
        print("[scheduler] No se obtuvieron activos válidos para enviar alerta por email.")


def run_scheduler_email_alert():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(dispatch_daily_alert_email())
    loop.close()

# Registrar el job en el planificador (a las 11:30 todos los días, después del refresh de 11:00)
scheduler.add_job(run_scheduler_email_alert, 'cron', day_of_week='mon-fri', hour=11, minute=30, id='daily_email_alert')

@app.post("/api/send-test-alert")
async def post_send_test_alert(background_tasks: BackgroundTasks):
    background_tasks.add_task(dispatch_daily_alert_email)
    return {"status": "started", "message": "Proceso de envío de emails de prueba iniciado en segundo plano."}

# ===== REFRESH =====
@app.post("/api/refresh")
async def trigger_refresh(background_tasks: BackgroundTasks):
    global is_updating
    if is_updating:
        return {"status": "in_progress", "message": "Actualización ya en curso."}
    background_tasks.add_task(refresh_all_data, force=True)
    return {"status": "started", "message": "Actualización manual en segundo plano iniciada."}
