"""
candlestick_scorer.py — Detector de Patrones de Velas Japonesas

Principio rector:
    - El patrón de velas NUNCA decide la compra/venta por sí solo.
    - Devuelve un subscore [0, 100] donde 50 = neutro (sin patrón).
    - Se suma como bonus aditivo al score compuesto del funnel:
        score_final = clamp(score_5dim + peso × (candle_subscore − 50), 0, 100)
    - Desactivar: establecer _CANDLE_WEIGHT = 0 en asset_funnel.py.

Patrones detectados (lógica OHLC pura, sin TA-Lib ni pandas-ta):
    Alcistas: bullish_engulfing, hammer, morning_star, piercing_line
    Neutros:  doji
    Bajistas: bearish_engulfing, shooting_star, evening_star, hanging_man

Amplificadores de contexto aplicados sobre la fuerza bruta del patrón:
    - Volumen relativo vs. promedio 20d
    - Proximidad al soporte/resistencia detectada en la ventana histórica
    - Confirmación de la vela siguiente (si hay datos disponibles)

Trazabilidad: el dict de detalle incluye:
    {
        "patron_detectado": str,   # nombre del patrón o "sin_patron"
        "fuerza_base": float,      # fuerza geométrica del patrón [0, 1]
        "contexto_mult": float,    # multiplicador por contexto [0.6, 1.5]
        "descripcion": str,        # texto human-readable para el frontend
    }
"""

import numpy as np
import pandas as pd


# ============================================================
# CONFIGURACIÓN
# ============================================================

# Umbrales geométricos para definir qué es un "cuerpo pequeño" o "sombra larga"
_DOJI_RATIO_MAX     = 0.10   # cuerpo ≤ 10% del rango H-L → doji
_HAMMER_SHADOW_MIN  = 2.0    # sombra inferior ≥ 2× cuerpo → hammer / hanging man
_ENGULF_RATIO_MIN   = 1.05   # vela envolvente ≥ 5% más grande que la anterior

# Amplificadores de contexto
_VOL_BOOST_THRESHOLD  = 1.5   # volumen 1.5× promedio → boost
_VOL_BOOST_FACTOR     = 1.30
_NEAR_SUPPORT_MAX_PCT = 0.05  # precio dentro del 5% del soporte → boost
_NEAR_SUPPORT_FACTOR  = 1.20
_FAR_SUPPORT_MIN_PCT  = 0.20  # precio más del 20% sobre el soporte → penalización
_FAR_SUPPORT_FACTOR   = 0.80
_CONFIRM_FACTOR       = 1.20  # vela siguiente confirma la dirección del patrón


# ============================================================
# HELPERS INTERNOS
# ============================================================

def _body(o: float, c: float) -> float:
    """Tamaño absoluto del cuerpo de la vela."""
    return abs(c - o)


def _range(h: float, l: float) -> float:
    """Rango completo de la vela (High - Low), evita div/0."""
    return max(h - l, 1e-9)


def _upper_shadow(o: float, h: float, c: float) -> float:
    """Sombra superior."""
    return h - max(o, c)


def _lower_shadow(o: float, l: float, c: float) -> float:
    """Sombra inferior."""
    return min(o, c) - l


def _is_bullish(o: float, c: float) -> bool:
    return c > o


def _is_bearish(o: float, c: float) -> bool:
    return c < o


# ============================================================
# DETECCIÓN DE PATRONES (sobre las últimas N velas del df)
# ============================================================

def _detect_pattern(df: pd.DataFrame) -> tuple[str, float]:
    """
    Detecta el patrón más relevante en las últimas 3 velas.

    Returns:
        (nombre_patron, fuerza_base [0, 1])
        fuerza_base:
            1.0 = patrón "perfecto"
            0.5 = patrón presente pero no limpio
            0.0 = sin patrón / no detectado
        nombre_patron: 'sin_patron' si no se detecta ninguno.
    """
    if len(df) < 3:
        return "sin_patron", 0.0

    # Extraer las 3 últimas velas
    row  = df.iloc[-1]   # vela actual (del día)
    row1 = df.iloc[-2]   # vela anterior
    row2 = df.iloc[-3]   # dos velas atrás

    o,  h,  l,  c  = float(row["Open"]),  float(row["High"]),  float(row["Low"]),  float(row["Close"])
    o1, h1, l1, c1 = float(row1["Open"]), float(row1["High"]), float(row1["Low"]), float(row1["Close"])
    o2, h2, l2, c2 = float(row2["Open"]), float(row2["High"]), float(row2["Low"]), float(row2["Close"])

    body  = _body(o, c);   r  = _range(h, l)
    body1 = _body(o1, c1); r1 = _range(h1, l1)
    body2 = _body(o2, c2); r2 = _range(h2, l2)

    # ── 1. DOJI (solo vela actual) ─────────────────────────
    if body / r <= _DOJI_RATIO_MAX:
        return "doji", 0.3   # patrón neutro, fuerza baja

    # ── 2. BULLISH ENGULFING (2 velas) ────────────────────
    if (
        _is_bearish(o1, c1) and _is_bullish(o, c)
        and o <= c1 and c >= o1            # envuelve el cuerpo anterior
        and body >= body1 * _ENGULF_RATIO_MIN
    ):
        fuerza = min(1.0, body / (body1 + 1e-9) * 0.6)
        return "bullish_engulfing", round(fuerza, 3)

    # ── 3. BEARISH ENGULFING (2 velas) ────────────────────
    if (
        _is_bullish(o1, c1) and _is_bearish(o, c)
        and o >= c1 and c <= o1
        and body >= body1 * _ENGULF_RATIO_MIN
    ):
        fuerza = min(1.0, body / (body1 + 1e-9) * 0.6)
        return "bearish_engulfing", round(fuerza, 3)

    # ── 4. HAMMER (mecha inferior larga en tendencia bajista) ─
    low_sh  = _lower_shadow(o, l, c)
    up_sh   = _upper_shadow(o, h, c)
    if (
        body > 0
        and low_sh >= body * _HAMMER_SHADOW_MIN
        and up_sh  <= body * 0.5
        and c1 < o1  # vela anterior bajista → contexto de tendencia
    ):
        fuerza = min(1.0, low_sh / (body + 1e-9) * 0.35)
        return "hammer", round(fuerza, 3)

    # ── 5. SHOOTING STAR (mecha superior larga en tendencia alcista) ─
    if (
        body > 0
        and up_sh  >= body * _HAMMER_SHADOW_MIN
        and low_sh <= body * 0.5
        and c1 > o1  # vela anterior alcista
    ):
        fuerza = min(1.0, up_sh / (body + 1e-9) * 0.35)
        return "shooting_star", round(fuerza, 3)

    # ── 6. HANGING MAN (igual a hammer pero en tendencia alcista) ─
    if (
        body > 0
        and low_sh >= body * _HAMMER_SHADOW_MIN
        and up_sh  <= body * 0.5
        and c1 > o1  # vela anterior alcista → señal bajista
    ):
        fuerza = min(1.0, low_sh / (body + 1e-9) * 0.30)
        return "hanging_man", round(fuerza, 3)

    # ── 7. PIERCING LINE (2 velas; alcista) ───────────────
    if (
        _is_bearish(o1, c1) and _is_bullish(o, c)
        and o < l1                          # abre bajo el mínimo anterior
        and c > (o1 + c1) / 2              # cierra por encima del punto medio
    ):
        penetration = (c - (o1 + c1) / 2) / (body1 + 1e-9)
        fuerza = min(1.0, penetration * 0.7)
        return "piercing_line", round(fuerza, 3)

    # ── 8. MORNING STAR (3 velas; alcista) ────────────────
    if (
        _is_bearish(o2, c2) and body2 > r2 * 0.4   # vela bajista grande
        and body1 / r1 <= 0.25                       # vela pequeña (indecisión)
        and _is_bullish(o, c) and body > r * 0.4    # vela alcista grande
        and c > (o2 + c2) / 2                        # cierra sobre 50% de vela 3
    ):
        fuerza = min(1.0, body / (body2 + 1e-9) * 0.5)
        return "morning_star", round(fuerza, 3)

    # ── 9. EVENING STAR (3 velas; bajista) ────────────────
    if (
        _is_bullish(o2, c2) and body2 > r2 * 0.4
        and body1 / r1 <= 0.25
        and _is_bearish(o, c) and body > r * 0.4
        and c < (o2 + c2) / 2
    ):
        fuerza = min(1.0, body / (body2 + 1e-9) * 0.5)
        return "evening_star", round(fuerza, 3)

    return "sin_patron", 0.0


# ============================================================
# AMPLIFICADORES DE CONTEXTO
# ============================================================

def _contexto_multiplier(df: pd.DataFrame, patron: str, fuerza: float) -> tuple[float, str]:
    """
    Calcula un multiplicador de contexto para la fuerza del patrón:
    - Volumen relativo
    - Posición respecto al soporte (sólo relevante para patrones alcistas)
    - Confirmación de la vela siguiente (si disponible)

    Returns:
        (mult, descripcion_contexto)
    """
    mult = 1.0
    ctx_parts = []

    close = df["Close"].dropna()
    volume = df["Volume"].dropna() if "Volume" in df.columns else pd.Series(dtype=float)

    # ── Volumen relativo ──────────────────────────────────────
    if not volume.empty and len(volume) >= 5:
        vol_hoy = float(volume.iloc[-1])
        vol_avg = float(volume.iloc[-21:-1].mean()) if len(volume) >= 21 else float(volume.mean())
        if vol_avg > 0:
            rel_vol = vol_hoy / vol_avg
            if rel_vol >= _VOL_BOOST_THRESHOLD:
                mult *= _VOL_BOOST_FACTOR
                ctx_parts.append(f"vol×{rel_vol:.1f}")

    # ── Proximidad al soporte ─────────────────────────────────
    is_bullish_pattern = patron in ("bullish_engulfing", "hammer", "morning_star", "piercing_line")
    if is_bullish_pattern and len(close) >= 20:
        lookback = close.iloc[-90:] if len(close) >= 90 else close
        support = float(np.percentile(lookback, 10))
        current = float(close.iloc[-1])
        if support > 0:
            dist_pct = (current - support) / current
            if dist_pct <= _NEAR_SUPPORT_MAX_PCT:
                mult *= _NEAR_SUPPORT_FACTOR
                ctx_parts.append("cerca_soporte")
            elif dist_pct >= _FAR_SUPPORT_MIN_PCT:
                mult *= _FAR_SUPPORT_FACTOR
                ctx_parts.append("lejos_soporte")

    # ── Confirmación de la vela siguiente ─────────────────────
    # Solo aplica si hay una vela posterior al patrón (útil en backtesting)
    # En tiempo real (última vela del día) no hay confirmación disponible aún.
    if len(df) >= 2 and patron != "sin_patron":
        c_confirm = float(df["Close"].iloc[-1])
        c_prev    = float(df["Close"].iloc[-2])
        # Patrón alcista confirmado si la última vela cierra más alto que la anterior
        if is_bullish_pattern and c_confirm > c_prev:
            mult *= _CONFIRM_FACTOR
            ctx_parts.append("confirmado")
        elif not is_bullish_pattern and patron not in ("doji", "sin_patron") and c_confirm < c_prev:
            mult *= _CONFIRM_FACTOR
            ctx_parts.append("confirmado")

    descripcion = ", ".join(ctx_parts) if ctx_parts else "sin_contexto_adicional"
    return round(mult, 3), descripcion


# ============================================================
# FUNCIÓN PÚBLICA
# ============================================================

# Sufijo de dirección de cada patrón
_PATTERN_DIRECTION = {
    "bullish_engulfing": 1,
    "hammer":            1,
    "morning_star":      1,
    "piercing_line":     1,
    "doji":              0,
    "sin_patron":        0,
    "bearish_engulfing": -1,
    "shooting_star":     -1,
    "evening_star":      -1,
    "hanging_man":       -1,
}

_PATTERN_DESCRIPTIONS = {
    "bullish_engulfing": "Envolvente alcista: vela alcista que supera la bajista anterior",
    "hammer":            "Martillo: sombra inferior larga en zona de soporte",
    "morning_star":      "Estrella de la mañana: reversión alcista de 3 velas",
    "piercing_line":     "Línea penetrante: apertura bajo mínimo y cierre sobre 50%",
    "doji":              "Doji: indecisión del mercado, cuerpo mínimo",
    "bearish_engulfing": "Envolvente bajista: vela bajista que supera la alcista anterior",
    "shooting_star":     "Estrella fugaz: sombra superior larga en zona de resistencia",
    "evening_star":      "Estrella vespertina: reversión bajista de 3 velas",
    "hanging_man":       "Hombre colgado: martillo en tendencia alcista (señal de techo)",
    "sin_patron":        "Sin patrón de velas relevante detectado",
}


def calcular_subscore_velas(
    df_ohlc: pd.DataFrame,
    config: dict | None = None,
) -> tuple[float, dict]:
    """
    Calcula el subscore de velas japonesas [0, 100] para integrar al score compuesto.

    Args:
        df_ohlc: DataFrame con columnas Open, High, Low, Close (y opcionalmente Volume).
                 Debe tener al menos 3 filas. Las filas deben estar ordenadas
                 cronológicamente (más antigua primero).
        config:  dict opcional para sobreescribir parámetros (futuro uso en backtesting).

    Returns:
        (subscore, detalle)
        subscore: float en [0, 100]
            50 = neutro (sin patrón o doji)
            > 50 = señal alcista (cuanto más alto, más fuerte)
            < 50 = señal bajista (cuanto más bajo, más fuerte)
        detalle: dict con:
            {
                "patron_detectado": str,
                "fuerza_base": float,
                "contexto_mult": float,
                "contexto_descripcion": str,
                "descripcion": str,
            }
    """
    # Validaciones mínimas
    required = {"Open", "High", "Low", "Close"}
    if df_ohlc is None or df_ohlc.empty or not required.issubset(df_ohlc.columns):
        return 50.0, {
            "patron_detectado": "sin_patron",
            "fuerza_base": 0.0,
            "contexto_mult": 1.0,
            "contexto_descripcion": "datos_insuficientes",
            "descripcion": _PATTERN_DESCRIPTIONS["sin_patron"],
        }

    try:
        patron, fuerza_base = _detect_pattern(df_ohlc)
    except Exception:
        patron, fuerza_base = "sin_patron", 0.0

    try:
        ctx_mult, ctx_desc = _contexto_multiplier(df_ohlc, patron, fuerza_base)
    except Exception:
        ctx_mult, ctx_desc = 1.0, "error_contexto"

    direccion = _PATTERN_DIRECTION.get(patron, 0)

    # score efectivo = fuerza ajustada por contexto, en [0, 1]
    fuerza_efectiva = min(1.0, fuerza_base * ctx_mult)

    # Mapear a [0, 100] centrado en 50:
    #   sin patrón → 50
    #   alcista máximo → 100
    #   bajista máximo → 0
    if direccion == 0:
        subscore = 50.0
    elif direccion == 1:
        # Alcista: 50 + fuerza_efectiva × 50
        subscore = 50.0 + fuerza_efectiva * 50.0
    else:
        # Bajista: 50 - fuerza_efectiva × 50
        subscore = 50.0 - fuerza_efectiva * 50.0

    subscore = max(0.0, min(100.0, round(subscore, 1)))

    detalle = {
        "patron_detectado": patron,
        "fuerza_base": round(fuerza_base, 3),
        "contexto_mult": ctx_mult,
        "contexto_descripcion": ctx_desc,
        "descripcion": _PATTERN_DESCRIPTIONS.get(patron, patron),
    }

    return subscore, detalle
