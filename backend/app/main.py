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
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(refresh_all_data(force=True))
    loop.close()

scheduler = BackgroundScheduler()
scheduler.add_job(run_scheduler_refresh, 'cron', hour=11, minute=0, id='daily_market_update')

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
        return {"status": "error", "message": f"Activo '{ticker}' no encontrado."}
    
    analysis = generate_asset_analysis(target, profile)
    return {"status": "success", "analysis": analysis}

# ===== PORTFOLIO OPTIMIZER (Markowitz) =====
@app.get("/api/optimize")
async def get_optimal_portfolio(
    profile: str = Query("moderado", regex="^(conservador|moderado|agresivo)$"),
    horizon: str = Query("medium", regex="^(short|medium|long)$")
):
    all_assets = await _get_all_assets()
    scored = get_recommendations_by_profile(all_assets, profile, horizon)
    top_assets = scored["top_10"]
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

# ===== PORTFOLIO (Mi Cartera) =====
@app.get("/api/portfolio")
async def get_portfolio(user: Optional[Dict] = Depends(get_current_user)):
    positions = await get_all_positions(user)
    all_assets = await _get_all_assets()
    price_map = {a["ticker"]: a["price"] for a in all_assets}
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

# ===== REFRESH =====
@app.post("/api/refresh")
async def trigger_refresh(background_tasks: BackgroundTasks):
    global is_updating
    if is_updating:
        return {"status": "in_progress", "message": "Actualización ya en curso."}
    background_tasks.add_task(refresh_all_data, force=True)
    return {"status": "started", "message": "Actualización manual en segundo plano iniciada."}
