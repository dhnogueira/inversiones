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
from app.services.market_screener import run_market_screener, run_screener_all_profiles

# Estado de carga de datos iniciales
is_updating = False

import json as _json
from datetime import datetime as _dt

SCHEDULER_LOG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "../cache/scheduler_log.json")
)

def _write_scheduler_log(event: str, status: str, detail: str = ""):
    """Escribe una entrada en el log de auditoría del scheduler."""
    entry = {
        "timestamp": _dt.now().isoformat(timespec="seconds"),
        "event": event,
        "status": status,
        "detail": detail,
    }
    log = []
    if os.path.exists(SCHEDULER_LOG_PATH):
        try:
            with open(SCHEDULER_LOG_PATH, "r", encoding="utf-8") as f:
                log = _json.load(f)
            if not isinstance(log, list):
                log = []
        except Exception:
            log = []
    log.append(entry)
    # Mantener solo los últimos 200 eventos
    log = log[-200:]
    try:
        with open(SCHEDULER_LOG_PATH, "w", encoding="utf-8") as f:
            _json.dump(log, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[scheduler] Error escribiendo audit log: {e}")


async def refresh_all_data(force=False):
    global is_updating
    if is_updating:
        print("Data update already in progress, skipping.")
        return
    is_updating = True
    try:
        print("Starting market data cache refresh...")
        await asyncio.gather(
            fetch_yfinance_market_data(force_refresh=force),
            fetch_arg_fixed_income_data(force_refresh=force)
        )
        print("Data refresh completed successfully.")
    except Exception as e:
        print(f"Error during market data refresh: {e}")
    finally:
        is_updating = False


def run_10min_cache_refresh():
    """
    Job de 10 minutos: SOLO refresca la caché en memoria/disco.
    NO ejecuta build_static.py (evita rate-limiting en Yahoo Finance).
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(refresh_all_data(force=True))
        _write_scheduler_log("cache_refresh_10min", "ok")
    except Exception as e:
        _write_scheduler_log("cache_refresh_10min", "error", str(e))
    finally:
        loop.close()


def run_daily_funnel_all():
    """
    Job diario a las 11:15 AM (lunes a viernes):
    Ejecuta el funnel de selección en cascada para los 9 combos
    perfil×horizonte (conservador/moderado/agresivo × short/medium/long)
    y guarda las cachés en disco.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_screener_all_profiles(force_refresh=True))
        _write_scheduler_log("funnel_all_profiles", "ok",
                             "Funnel 9× combos completado exitosamente.")
        print("[daily_funnel] Funnel 9× combos completado.")
    except Exception as e:
        _write_scheduler_log("funnel_all_profiles", "error", str(e))
        print(f"[daily_funnel] Error: {e}")
    finally:
        loop.close()


def run_daily_full_build():
    """
    Job diario a las 11:00 AM (lunes a viernes):
    1. Refresca la caché de datos de mercado.
    2. Ejecuta build_static.py → recalcula Markowitz + clasificación por categoría
       para todos los perfiles, horizontes y categorías.
    3. Hace git add + commit + push para actualizar GitHub Pages.
    4. Escribe una entrada en el log de auditoría.
    """
    import sys
    import subprocess

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root_dir = os.path.dirname(backend_dir)

    print("[daily_build] Iniciando rebuild diario completo (Markowitz + clasificación)...")
    _write_scheduler_log("daily_full_build", "started")

    # 1. Actualizar caché
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(refresh_all_data(force=True))
    except Exception as e:
        _write_scheduler_log("daily_full_build", "error", f"cache refresh failed: {e}")
        return
    finally:
        loop.close()

    # 2. Compilar archivos estáticos → Markowitz + clasificaciones
    build_ok = False
    try:
        python_executable = sys.executable or "python"
        build_script = os.path.join(backend_dir, "build_static.py")
        print(f"[daily_build] Ejecutando: {python_executable} {build_script}")
        res_build = subprocess.run(
            [python_executable, build_script],
            capture_output=True, text=True, cwd=backend_dir
        )
        if res_build.returncode == 0:
            print("[daily_build] Compilación estática completada exitosamente.")
            build_ok = True
        else:
            err = res_build.stderr[-500:] if res_build.stderr else ""
            print(f"[daily_build] Error en compilación (código {res_build.returncode}): {err}")
            _write_scheduler_log("daily_full_build", "error", f"build_static.py failed: {err}")
            return
    except Exception as e:
        _write_scheduler_log("daily_full_build", "error", f"build exception: {e}")
        return

    # 3. Git add + commit + push
    try:
        subprocess.run(["git", "add", "frontend/api/"], capture_output=True, text=True, cwd=root_dir)
        status_res = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=root_dir
        )
        staged_changes = [
            line for line in status_res.stdout.splitlines()
            if line.startswith(('M ', 'A ', 'D ', 'MM', 'AM'))
        ]

        commit_ok = False
        if staged_changes:
            ts = _dt.now().strftime("%Y-%m-%d %H:%M")
            git_commit = subprocess.run(
                ["git", "commit", "-m", f"data: daily market update {ts} (Markowitz+clasificacion)"],
                capture_output=True, text=True, cwd=root_dir
            )
            print(f"[daily_build] Git commit: {git_commit.stdout.strip()}")
            commit_ok = git_commit.returncode == 0
        else:
            print("[daily_build] Sin cambios nuevos para commitear.")
            commit_ok = True

        # Push siempre (commit o no) para garantizar sincronización
        git_push = subprocess.run(
            ["git", "push", "origin", "main"],
            capture_output=True, text=True, cwd=root_dir
        )
        if git_push.returncode == 0:
            print("[daily_build] Git push exitoso.")
            _write_scheduler_log(
                "daily_full_build", "ok",
                f"{len(staged_changes)} archivos actualizados. Push: ok."
            )
        else:
            push_err = git_push.stderr[-300:] if git_push.stderr else ""
            print(f"[daily_build] Git push falló: {push_err}")
            _write_scheduler_log("daily_full_build", "warning", f"commit ok, push failed: {push_err}")

    except Exception as e:
        _write_scheduler_log("daily_full_build", "error", f"git step failed: {e}")
        print(f"[daily_build] Error en paso git: {e}")


scheduler = BackgroundScheduler()
# Job 1: Refresco de caché cada 10 minutos (solo cache, sin rebuild completo)
scheduler.add_job(run_10min_cache_refresh, 'interval', minutes=10, id='market_data_10_min')
# Job 2: Rebuild diario completo a las 11:00 AM (lun-vie): Markowitz + clasificaciones + git push
scheduler.add_job(run_daily_full_build, 'cron', day_of_week='mon-fri', hour=11, minute=0, id='daily_full_build')
# Job 3: Funnel de screening a las 11:15 AM (lun-vie): 9 combos perfil×horizonte
scheduler.add_job(run_daily_funnel_all, 'cron', day_of_week='mon-fri', hour=11, minute=15, id='daily_funnel_all')

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

# ===== SCHEDULER AUDIT LOG =====
@app.get("/api/scheduler-log")
def read_scheduler_log(limit: int = Query(50, ge=1, le=200)):
    """Devuelve las últimas entradas del log de auditoría del scheduler (Markowitz + clasificación diaria)."""
    if not os.path.exists(SCHEDULER_LOG_PATH):
        return {"status": "ok", "log": [], "message": "Sin entradas de log todavía."}
    try:
        with open(SCHEDULER_LOG_PATH, "r", encoding="utf-8") as f:
            log = _json.load(f)
        if not isinstance(log, list):
            log = []
        return {"status": "ok", "count": len(log), "log": log[-limit:]}
    except Exception as e:
        return {"status": "error", "message": str(e)}


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

# ===== MARKET SCREENER (Funnel de selección en cascada) =====
@app.get("/api/screener")
async def get_screener(
    profile: str = Query("moderado", regex="^(conservador|moderado|agresivo)$"),
    horizon: str = Query("medium", regex="^(short|medium|long)$"),
    force: bool = Query(False)
):
    """
    Ejecuta el funnel de 3 etapas (liquidez → técnico grueso → scoring compuesto)
    y retorna los mejores activos del universo para el perfil y horizonte indicados.

    Los umbrales, pesos y cantidad de resultados varían según perfil e horizonte:
    - conservador: umbrales de liquidez altos, score mín. 55, top 5 por categoría
    - moderado:    umbrales intermedios, score mín. 45, top 8 por categoría
    - agresivo:    umbrales bajos (más oportunidades), score mín. 35, top 10 por categoría

    short   → pesa más momentum y cercanía al soporte
    medium  → pesa más EMA cross y Sharpe
    long    → pesa más Sharpe y retorno ajustado
    """
    result = await run_market_screener(profile=profile, horizon=horizon, force_refresh=force)
    return {"status": "success", **result}


@app.get("/api/funnel-status")
async def get_funnel_status(
    profile: str = Query("moderado", regex="^(conservador|moderado|agresivo)$"),
    horizon: str = Query("medium", regex="^(short|medium|long)$")
):
    """
    Retorna las métricas del último run del funnel (cuántos tickers
    pasaron cada etapa) sin volver a ejecutarlo.
    """
    import json as _json_inner
    from app.config import CACHE_DIR as _CACHE_DIR
    cache_key = f"funnel_{profile}_{horizon}.json"
    cache_path = os.path.join(_CACHE_DIR, cache_key)
    if not os.path.exists(cache_path):
        return {
            "status": "not_run",
            "message": f"El funnel para '{profile}/{horizon}' no ha sido ejecutado todavía.",
            "profile": profile,
            "horizon": horizon,
        }
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = _json_inner.load(f)
        pipeline = data.get("pipeline", {})
        results = data.get("results", {})
        summary = {cat: len(assets) for cat, assets in results.items()}
        return {
            "status": "ok",
            "pipeline": pipeline,
            "results_summary": summary,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/screener/refresh")
async def trigger_screener_refresh(
    background_tasks: BackgroundTasks,
    profile: str = Query("moderado", regex="^(conservador|moderado|agresivo)$"),
    horizon: str = Query("medium", regex="^(short|medium|long)$")
):
    """Dispara la re-ejecución del funnel para un combo perfil/horizonte en segundo plano."""
    background_tasks.add_task(run_market_screener, profile=profile, horizon=horizon, force_refresh=True)
    return {"status": "started", "message": f"Funnel {profile}/{horizon} iniciado en segundo plano."}


# ===== REFRESH =====
@app.post("/api/refresh")
async def trigger_refresh(background_tasks: BackgroundTasks):
    global is_updating
    if is_updating:
        return {"status": "in_progress", "message": "Actualización ya en curso."}
    background_tasks.add_task(refresh_all_data, force=True)
    return {"status": "started", "message": "Actualización manual en segundo plano iniciada."}
