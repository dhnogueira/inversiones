"""
Script to generate market-screener static JSON files for all 9 profile x horizon combinations.
Uses the backend recommendations API to populate the screener files.
"""
import os
import sys
import json
import time
import math

# Ensure we can import from the backend
BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
sys.path.insert(0, BACKEND_DIR)

FRONTEND_API_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "api")

PROFILES = ["conservador", "moderado", "agresivo"]
HORIZONS = ["short", "medium", "long"]


def safe_float(v, default=0.0):
    if v is None:
        return default
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def build_screener_entry(asset, funnel_score=None):
    """Convert a recommendation asset into a screener entry format."""
    score = funnel_score if funnel_score is not None else safe_float(asset.get("score"), 0)
    return {
        "ticker": asset.get("ticker", ""),
        "name": asset.get("name", asset.get("ticker", "")),
        "category": asset.get("category", ""),
        "price": safe_float(asset.get("price"), 0),
        "currency": asset.get("currency", "ARS"),
        "funnel_score": round(score, 1),
        "ret_1m": safe_float(asset.get("ret_1m"), 0),
        "ret_12m": safe_float(asset.get("ret_12m"), 0),
        "volatility": safe_float(asset.get("volatility"), 0.25),
        "sharpe": safe_float(asset.get("sharpe"), 0),
        "rsi": safe_float(asset.get("rsi"), 50),
        "trend": asset.get("trend", "Alcista"),
        "ema_50": safe_float(asset.get("ema_50"), 0),
        "ema_200": safe_float(asset.get("ema_200"), 0),
        "momentum_accel": safe_float(asset.get("momentum_accel"), 0),
        "dist_to_support_pct": safe_float(asset.get("dist_to_support_pct"), 0.1),
        "dist_to_resistance_pct": safe_float(asset.get("dist_to_resistance_pct"), 0.1),
        "dollar_vol_20d": safe_float(asset.get("dollar_vol_20d"), 0),
        "ret_6m": safe_float(asset.get("ret_6m"), 0),
        "drawdown_pct": safe_float(asset.get("drawdown_pct"), 0),
        "profile": asset.get("profile", "moderado"),
        "horizon": asset.get("horizon", "medium"),
        "timestamp": asset.get("timestamp", time.time()),
    }


def generate_screener_json(profile, horizon, market_data):
    """Generate the screener JSON from recommendation data."""
    from app.scoring.profiles import get_recommendations_by_profile

    results = get_recommendations_by_profile(market_data, profile, horizon)
    categories = results.get("categories", {})

    results_by_cat = {}
    for cat, assets in categories.items():
        # Use top assets (those with score > 0, sorted by score)
        valid = [a for a in assets if a.get("score", 0) > 0]
        valid.sort(key=lambda x: x.get("score", 0), reverse=True)
        top_n = {"conservador": 5, "moderado": 8, "agresivo": 10}.get(profile, 8)
        results_by_cat[cat] = [build_screener_entry(a, a.get("score")) for a in valid[:top_n]]

    total = sum(len(v) for v in results_by_cat.values())
    output = {
        "status": "success",
        "pipeline": {
            "universe_size": sum(len(v) for v in categories.values()),
            "stage1_passed": total,
            "stage2_passed": total,
            "final_count": total,
            "timestamp": time.time(),
            "profile": profile,
            "horizon": horizon,
        },
        "results": results_by_cat,
        # Keep legacy 'categories' key for compatibility
        "categories": results_by_cat,
    }
    return output


def main():
    # Load cached market data
    from app.services.yfinance_service import fetch_yfinance_market_data
    from app.services.arg_fixed_income import fetch_arg_fixed_income_data
    import asyncio

    print("Loading cached market data...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        yf_data = loop.run_until_complete(fetch_yfinance_market_data(use_cache_only=True))
        fi_data = loop.run_until_complete(fetch_arg_fixed_income_data(force_refresh=False))
    finally:
        loop.close()

    all_assets = yf_data + fi_data
    print(f"Loaded {len(all_assets)} assets from cache.")

    if len(all_assets) == 0:
        print("ERROR: No assets loaded from cache. Cannot generate screener files.")
        return

    for profile in PROFILES:
        for horizon in HORIZONS:
            print(f"Generating screener for {profile}/{horizon}...")
            try:
                data = generate_screener_json(profile, horizon, all_assets)
                total = data["pipeline"]["final_count"]
                filename = f"market-screener-{profile}-{horizon}.json"
                path = os.path.join(FRONTEND_API_DIR, filename)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"  -> {filename}: {total} oportunidades escritas.")
            except Exception as e:
                print(f"  -> ERROR en {profile}/{horizon}: {e}")
                import traceback
                traceback.print_exc()

    # Also update the generic screener file
    try:
        data = generate_screener_json("moderado", "medium", all_assets)
        with open(os.path.join(FRONTEND_API_DIR, "market-screener.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("market-screener.json updated.")
    except Exception as e:
        print(f"ERROR updating market-screener.json: {e}")

    print("\nDone! All screener files generated.")


if __name__ == "__main__":
    main()
