"""
backtest_candles.py — Backtest comparativo: score sin velas vs. score con velas

Mide si el componente de velas japonesas mejora la calidad del ranking del funnel.

Métricas:
    precision@k:  % de activos en el top-K que subieron en los N días siguientes.
    hit_rate:     % de activos sugeridos con retorno positivo (todos los seleccionados).
    rank_delta:   correlación de Spearman entre el ranking con/sin velas y el retorno real.

Uso:
    cd PicadoFino/backend
    python backtest_candles.py
    python backtest_candles.py --profile agresivo --horizon short --topk 10 --forward_days 20
"""

import argparse
import os
import sys
import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import spearmanr

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.asset_funnel import (
    FULL_UNIVERSE, _CATEGORIES,
    _stage1_liquidity, _stage2_technical,
    _compute_full_metrics, _stage3_composite_score,
    _CANDLE_WEIGHT,
)
from app.services.candlestick_scorer import calcular_subscore_velas


# ── Configuración por defecto ─────────────────────────────────────────────────
DEFAULT_PROFILE      = "moderado"
DEFAULT_HORIZON      = "medium"
DEFAULT_TOP_K        = 8
DEFAULT_FORWARD_DAYS = 15   # días hábiles hacia adelante para medir retorno
BACKTEST_PERIOD      = "2y" # histórico a descargar


def _download_data(tickers: list[str]) -> dict:
    """Descarga en batch y devuelve dict {ticker: DataFrame}."""
    print(f"Descargando {len(tickers)} tickers ({BACKTEST_PERIOD})...")
    raw = yf.download(
        tickers,
        period=BACKTEST_PERIOD,
        interval="1d",
        group_by="ticker",
        progress=False,
        timeout=120,
    )
    result = {}
    for t in tickers:
        try:
            df = raw[t].dropna(subset=["Close"]) if t in raw.columns.get_level_values(0) else pd.DataFrame()
            if not df.empty:
                result[t] = df
        except Exception:
            pass
    print(f"  => Datos disponibles para {len(result)} / {len(tickers)} tickers")
    return result


def _score_at_date(
    df_full: pd.DataFrame,
    end_idx: int,
    ticker: str,
    category: str,
    profile: str,
    horizon: str,
    with_candles: bool,
) -> float | None:
    """Calcula el score del sistema hasta el índice end_idx del df."""
    df_slice = df_full.iloc[:end_idx]
    if len(df_slice) < 60:
        return None
    metrics = _compute_full_metrics(ticker, df_slice, category)
    if metrics is None:
        return None

    if with_candles:
        score, _ = _stage3_composite_score(metrics, profile, horizon, df=df_slice)
    else:
        # Fuerza candle_weight=0 temporalmente
        from app.services import asset_funnel as af
        original_weight = af._CANDLE_WEIGHT
        af._CANDLE_WEIGHT = 0.0
        score, _ = _stage3_composite_score(metrics, profile, horizon, df=df_slice)
        af._CANDLE_WEIGHT = original_weight
    return score


def _forward_return(df_full: pd.DataFrame, end_idx: int, forward_days: int) -> float | None:
    """Retorno porcentual de los próximos 'forward_days' días hábiles."""
    if end_idx >= len(df_full) - forward_days:
        return None
    c0 = float(df_full["Close"].iloc[end_idx - 1])
    cf = float(df_full["Close"].iloc[end_idx - 1 + forward_days])
    if c0 <= 0:
        return None
    return (cf - c0) / c0


def run_backtest(
    profile: str = DEFAULT_PROFILE,
    horizon: str = DEFAULT_HORIZON,
    top_k: int = DEFAULT_TOP_K,
    forward_days: int = DEFAULT_FORWARD_DAYS,
) -> dict:
    # 1. Filtrar el universo con Etapas 1 y 2 para tener el mismo subconjunto
    print(f"\n[backtest] Perfil={profile} | Horizonte={horizon} | Top-K={top_k} | FwdDays={forward_days}\n")

    all_data = _download_data(FULL_UNIVERSE)

    candidates = {}
    for ticker, df in all_data.items():
        cat = _CATEGORIES.get(ticker, "sp500")
        if _stage1_liquidity(ticker, df, cat, profile) and _stage2_technical(ticker, df, horizon):
            candidates[ticker] = (df, cat)
    print(f"[backtest] {len(candidates)} candidatos pasaron Etapas 1+2\n")

    if not candidates:
        print("[backtest] Sin candidatos. Revisar universo o parámetros.")
        return {}

    # 2. Simular en un punto de corte: última fecha con datos disponibles para forward
    results = []
    for ticker, (df, cat) in candidates.items():
        # Usar el penúltimo bloque para asegurar que hay datos futuros
        end_idx = len(df) - forward_days
        if end_idx < 60:
            continue

        score_sin = _score_at_date(df, end_idx, ticker, cat, profile, horizon, with_candles=False)
        score_con = _score_at_date(df, end_idx, ticker, cat, profile, horizon, with_candles=True)
        ret       = _forward_return(df, end_idx, forward_days)

        if score_sin is None or score_con is None or ret is None:
            continue

        # Subscore de velas en ese momento
        df_slice = df.iloc[:end_idx]
        candle_sub, candle_det = calcular_subscore_velas(df_slice)

        results.append({
            "ticker":       ticker,
            "category":     cat,
            "score_sin":    score_sin,
            "score_con":    score_con,
            "score_delta":  round(score_con - score_sin, 2),
            "candle_sub":   round(candle_sub, 1),
            "patron":       candle_det.get("patron_detectado", "sin_patron"),
            "forward_ret":  round(ret, 4),
            "went_up":      ret > 0,
        })

    if not results:
        print("[backtest] Sin resultados con suficiente historial.")
        return {}

    df_res = pd.DataFrame(results).sort_values("score_con", ascending=False)

    print(f"  {'TICKER':<10} {'CAT':<8} {'SIN':<7} {'CON':<7} {'DELTA':<7} {'VELAS':<7} {'PATRON':<22} {'RET_FWD'}")
    print("  " + "-" * 85)
    for _, row in df_res.head(20).iterrows():
        print(
            f"  {row['ticker']:<10} {row['category']:<8} "
            f"{row['score_sin']:<7.1f} {row['score_con']:<7.1f} "
            f"{row['score_delta']:<+7.2f} {row['candle_sub']:<7.1f} "
            f"{row['patron']:<22} {row['forward_ret']:>+.2%}"
        )

    # 3. Métricas comparativas
    top_k_sin = df_res.nlargest(top_k, "score_sin")
    top_k_con = df_res.nlargest(top_k, "score_con")

    precision_sin = top_k_sin["went_up"].mean()
    precision_con = top_k_con["went_up"].mean()

    hit_all_sin = df_res[df_res["score_sin"] > 45]["went_up"].mean()
    hit_all_con = df_res[df_res["score_con"] > 45]["went_up"].mean()

    spear_sin, _ = spearmanr(df_res["score_sin"], df_res["forward_ret"])
    spear_con, _ = spearmanr(df_res["score_con"], df_res["forward_ret"])

    # 4. Patrones activos en el top-K final
    patron_dist = df_res.head(top_k * 2)["patron"].value_counts()

    print(f"\n{'='*60}")
    print(f"  BACKTEST COMPARATIVO CON vs. SIN VELAS  (peso={int(_CANDLE_WEIGHT*100)}%)")
    print(f"{'='*60}")
    print(f"  Candidatos analizados : {len(df_res)}")
    print(f"  Horizonte de evaluación: {forward_days} días hábiles")
    print()
    print(f"  Precisión@{top_k} (sin velas): {precision_sin:.1%}")
    print(f"  Precisión@{top_k} (con velas): {precision_con:.1%}  {'✅ MEJORA' if precision_con > precision_sin else '⚠️  SIN MEJORA'}")
    print()
    print(f"  Hit rate todos (sin velas): {hit_all_sin:.1%}")
    print(f"  Hit rate todos (con velas): {hit_all_con:.1%}  {'✅ MEJORA' if hit_all_con > hit_all_sin else '⚠️  SIN MEJORA'}")
    print()
    print(f"  Spearman (sin velas): {spear_sin:.3f}")
    print(f"  Spearman (con velas): {spear_con:.3f}  {'✅ MEJORA' if spear_con > spear_sin else '⚠️  SIN MEJORA'}")
    print()
    print(f"  Distribución de patrones en top-{top_k*2}:")
    for pat, cnt in patron_dist.items():
        print(f"    {pat:<25} {cnt}")
    print(f"{'='*60}\n")

    # 5. Recomendación automática sobre el peso
    if precision_con > precision_sin and spear_con > spear_sin:
        rec = f"✅ El componente de velas MEJORA el sistema. Mantener peso={int(_CANDLE_WEIGHT*100)}% o subir hasta 15%."
    elif precision_con >= precision_sin:
        rec = f"◎ El componente de velas no empeora el sistema. Mantener con peso conservador={int(_CANDLE_WEIGHT*100)}%."
    else:
        rec = f"⚠️  El componente de velas EMPEORA en este contexto. Considerar bajar _CANDLE_WEIGHT a 0.05 o a 0.0."
    print(f"  Recomendación: {rec}\n")

    return {
        "n_candidates":    len(df_res),
        "precision_sin":   round(precision_sin, 4),
        "precision_con":   round(precision_con, 4),
        "hit_sin":         round(hit_all_sin, 4),
        "hit_con":         round(hit_all_con, 4),
        "spearman_sin":    round(spear_sin, 4),
        "spearman_con":    round(spear_con, 4),
        "recomendacion":   rec,
        "patron_dist":     patron_dist.to_dict(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backtest: score con vs. sin velas japonesas")
    parser.add_argument("--profile",      default=DEFAULT_PROFILE,      choices=["conservador", "moderado", "agresivo"])
    parser.add_argument("--horizon",      default=DEFAULT_HORIZON,      choices=["short", "medium", "long"])
    parser.add_argument("--topk",         default=DEFAULT_TOP_K,        type=int)
    parser.add_argument("--forward_days", default=DEFAULT_FORWARD_DAYS, type=int)
    args = parser.parse_args()

    run_backtest(
        profile=args.profile,
        horizon=args.horizon,
        top_k=args.topk,
        forward_days=args.forward_days,
    )
