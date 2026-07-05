"""
Servicio de Alertas por Email — Inversiones Picado Fino
Envía un resumen diario con el Top 5 de activos recomendados del día.
"""
import os
import json
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import (
    CACHE_DIR,
    ALERT_EMAIL_FROM,
    ALERT_EMAIL_PASSWORD,
    ALERT_EMAIL_SMTP_HOST,
    ALERT_EMAIL_SMTP_PORT,
    SITE_URL,
)

SUBSCRIBERS_FILE = os.path.join(CACHE_DIR, "subscribers.json")
ALERT_HISTORY_FILE = os.path.join(CACHE_DIR, "alert_history.json")

# Configuración de Supabase para leer suscriptores cloud
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")


# ──────────────────────────────────────────────────────────────────────────────
# Gestión de suscriptores
# ──────────────────────────────────────────────────────────────────────────────

def get_subscribers() -> list[str]:
    """
    Retorna la lista de emails suscriptos.
    Prioridad: Supabase (cloud) → archivo local (fallback).
    """
    # Intentar Supabase primero
    if SUPABASE_URL and SUPABASE_ANON_KEY:
        try:
            import httpx
            url = f"{SUPABASE_URL}/rest/v1/subscribers?select=email&active=eq.true"
            headers = {
                "apikey": SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            }
            r = httpx.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                rows = r.json()
                emails = [row["email"] for row in rows if row.get("email")]
                print(f"[email_service] {len(emails)} suscriptores cargados desde Supabase.")
                return emails
            else:
                print(f"[email_service] Error Supabase {r.status_code}, usando fallback local.")
        except Exception as e:
            print(f"[email_service] Error conectando a Supabase: {e}. Usando fallback local.")

    # Fallback: archivo local
    if not os.path.exists(SUBSCRIBERS_FILE):
        return []
    try:
        with open(SUBSCRIBERS_FILE, "r") as f:
            return json.load(f).get("emails", [])
    except Exception as e:
        print(f"[email_service] Error leyendo suscriptores locales: {e}")
        return []


def add_subscriber(email: str) -> dict:
    """Agrega un email al archivo local. La suscripción principal es vía Supabase desde el frontend."""
    email = email.strip().lower()
    subscribers = get_subscribers()
    if email in subscribers:
        return {"status": "already_subscribed", "email": email}
    # Guardar en archivo local como respaldo
    local_subs = []
    if os.path.exists(SUBSCRIBERS_FILE):
        try:
            with open(SUBSCRIBERS_FILE, "r") as f:
                local_subs = json.load(f).get("emails", [])
        except Exception:
            pass
    if email not in local_subs:
        local_subs.append(email)
        with open(SUBSCRIBERS_FILE, "w") as f:
            json.dump({"emails": local_subs}, f, indent=2)
    return {"status": "subscribed", "email": email}


def remove_subscriber(email: str) -> dict:
    """Elimina un email de la lista local."""
    email = email.strip().lower()
    if not os.path.exists(SUBSCRIBERS_FILE):
        return {"status": "not_found", "email": email}
    try:
        with open(SUBSCRIBERS_FILE, "r") as f:
            subscribers = json.load(f).get("emails", [])
    except Exception:
        return {"status": "not_found", "email": email}
    if email not in subscribers:
        return {"status": "not_found", "email": email}
    subscribers.remove(email)
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump({"emails": subscribers}, f, indent=2)
    return {"status": "unsubscribed", "email": email}


# ──────────────────────────────────────────────────────────────────────────────
# Historial de alertas
# ──────────────────────────────────────────────────────────────────────────────

def load_alert_history() -> list:
    """Retorna el historial de alertas enviadas (más reciente primero)."""
    if not os.path.exists(ALERT_HISTORY_FILE):
        return []
    try:
        with open(ALERT_HISTORY_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[email_service] Error leyendo historial: {e}")
        return []


def log_alert_dispatch(top5: list, recipient_count: int) -> dict:
    """Guarda un registro del envío en alert_history.json."""
    now = datetime.now()
    entry = {
        "sent_at": now.isoformat(timespec="seconds"),
        "sent_at_human": now.strftime("%d/%m/%Y %H:%M"),
        "subject": f"📈 Top 5 del día — {now.strftime('%d %b %Y')}",
        "recipient_count": recipient_count,
        "assets": [
            {
                "ticker": a.get("ticker", ""),
                "name": a.get("name", ""),
                "score": a.get("score", 0),
                "category": a.get("category", ""),
                "price": a.get("price", 0),
                "summary": _build_asset_summary(a),
            }
            for a in top5
        ],
    }
    history = load_alert_history()
    history.insert(0, entry)  # más reciente primero
    history = history[:30]    # conservar últimas 30 entradas
    with open(ALERT_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    return entry


def _build_asset_summary(asset: dict) -> str:
    """Genera un resumen breve de texto para el activo."""
    parts = []
    score = asset.get("score", 0)
    rsi = asset.get("rsi", None)
    trend = asset.get("trend", "")
    support = asset.get("support", None)
    resistance = asset.get("resistance", None)

    if score:
        parts.append(f"Score cuantitativo: {score:.1f}/100")
    if rsi:
        tag = "sobrevendido 📉" if rsi < 35 else ("sobrecomprado 📈" if rsi > 65 else "neutro")
        parts.append(f"RSI {rsi:.0f} ({tag})")
    if trend:
        parts.append(f"Tendencia: {trend}")
    if support:
        parts.append(f"Soporte: ${support:.2f}")
    if resistance:
        parts.append(f"Resistencia: ${resistance:.2f}")

    return " · ".join(parts) if parts else "Análisis técnico disponible en el sitio."


CATEGORY_ORDER = ["merval", "cedears", "sp500", "letras", "bonos", "crypto"]

CATEGORY_LABELS = {
    "sp500": "S&P 500",
    "cedears": "CEDEAR",
    "merval": "Merval",
    "bonos": "Bono",
    "letras": "Letra",
    "crypto": "Cripto",
}

CATEGORY_COLORS = {
    "sp500": "#3b82f6",
    "cedears": "#8b5cf6",
    "merval": "#06b6d4",
    "bonos": "#f59e0b",
    "letras": "#10b981",
    "crypto": "#f97316",
}

CATEGORY_ICONS = {
    "sp500": "🇺🇸",
    "cedears": "💼",
    "merval": "📈",
    "bonos": "💵",
    "letras": "📄",
    "crypto": "🪙",
}


def log_alert_dispatch(categorized_assets: dict, recipient_count: int) -> dict:
    """Guarda un registro del envío en alert_history.json."""
    now = datetime.now()
    flat_assets = []
    for cat in CATEGORY_ORDER:
        if cat in categorized_assets:
            for a in categorized_assets[cat]:
                flat_assets.append({
                    "ticker": a.get("ticker", ""),
                    "name": a.get("name", ""),
                    "score": a.get("score", 0),
                    "category": a.get("category", ""),
                    "price": a.get("price", 0),
                    "summary": _build_asset_summary(a),
                })

    entry = {
        "sent_at": now.isoformat(timespec="seconds"),
        "sent_at_human": now.strftime("%d/%m/%Y %H:%M"),
        "subject": f"📈 Resumen del Mercado — {now.strftime('%d %b %Y')}",
        "recipient_count": recipient_count,
        "assets": flat_assets,
    }
    history = load_alert_history()
    history.insert(0, entry)  # más reciente primero
    history = history[:30]    # conservar últimas 30 entradas
    with open(ALERT_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    return entry


def _build_asset_summary(asset: dict) -> str:
    """Genera un resumen breve de texto para el activo."""
    parts = []
    score = asset.get("score", 0)
    rsi = asset.get("rsi", None)
    trend = asset.get("trend", "")
    support = asset.get("support", None)
    resistance = asset.get("resistance", None)

    if score:
        parts.append(f"Score: {score:.1f}")
    if rsi:
        tag = "sobrevendido 📉" if rsi < 35 else ("sobrecomprado 📈" if rsi > 65 else "neutro")
        parts.append(f"RSI {rsi:.0f} ({tag})")
    if trend:
        parts.append(f"Tendencia: {trend}")
    if support:
        parts.append(f"Soporte: ${support:.2f}")
    if resistance:
        parts.append(f"Resist.: ${resistance:.2f}")

    return " · ".join(parts) if parts else "Análisis técnico disponible en el sitio."


def _build_email_html(categorized_assets: dict, date_str: str) -> str:
    categories_html = ""
    for category in CATEGORY_ORDER:
        if category not in categorized_assets or not categorized_assets[category]:
            continue

        cat_label = CATEGORY_LABELS.get(category, category.upper())
        cat_color = CATEGORY_COLORS.get(category, "#64748b")
        cat_icon = CATEGORY_ICONS.get(category, "⭐")

        rows_html = ""
        for a in categorized_assets[category]:
            ticker = a.get("ticker", "")
            name = a.get("name", ticker)
            score = a.get("score", 0)
            price = a.get("price", 0)
            summary = _build_asset_summary(a)
            modal_url = f"{SITE_URL}#modal={ticker}"

            rows_html += f"""
            <tr style="border-bottom: 1px solid #1f2937;">
              <td style="padding: 10px 14px; vertical-align: middle;">
                <div style="font-size: 15px; font-weight: bold; color: #fff;">
                  {ticker} <span style="font-size: 12px; color: #94a3b8; font-weight: normal;">{name}</span>
                </div>
                <div style="font-size: 11px; color: #94a3b8; margin-top: 2px; line-height: 1.4;">{summary}</div>
              </td>
              <td style="padding: 10px 14px; vertical-align: middle; text-align: right; white-space: nowrap;">
                <div style="font-size: 14px; font-weight: 700; color: #10b981;">${price:,.2f}</div>
                <div style="font-size: 11px; color: #64748b; margin-top: 1px;">Score: {score:.1f}</div>
              </td>
              <td style="padding: 10px 14px; vertical-align: middle; text-align: right; width: 45px;">
                 <a href="{modal_url}" style="display: inline-block; background: #2563eb; color: #fff; text-decoration: none; font-size: 11px; font-weight: bold; padding: 4px 10px; border-radius: 6px;">Ver</a>
              </td>
            </tr>
            """

        categories_html += f"""
        <!-- Category: {cat_label} -->
        <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse; margin-bottom: 24px; border: 1px solid #1e2d3e; border-radius: 10px; overflow: hidden; background: #111827;">
          <thead>
            <tr style="background: #1f2937; border-bottom: 2px solid {cat_color};">
              <th colspan="3" style="padding: 12px 14px; text-align: left;">
                <span style="font-size: 14px; font-weight: 800; color: #fff; text-transform: uppercase; letter-spacing: 1px;">{cat_icon} {cat_label} (Top 5)</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows_html}
          </tbody>
        </table>
        """

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>📈 Resumen de Mercado — Inversiones Picado Fino</title>
</head>
<body style="margin:0; padding:0; background:#0d111a; font-family:'Segoe UI', Arial, sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:32px 16px; background-color:#0d111a;">
    <tr>
      <td align="center">
        <!-- Header -->
        <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px; width:100%;">
          <tr>
            <td style="background: linear-gradient(135deg, #1e2d3e 0%, #0d111a 100%); border-radius:16px 16px 0 0; padding:28px 32px; text-align:center; border:1px solid #1e3a5f; border-bottom:none;">
              <div style="font-size:13px; color:#64748b; margin-bottom:6px; text-transform:uppercase; letter-spacing:2px;">Inversiones Picado Fino 🥩</div>
              <div style="font-size:26px; font-weight:800; color:#fff;">📈 Resumen Diario por Categorías</div>
              <div style="font-size:14px; color:#94a3b8; margin-top:6px;">{date_str}</div>
            </td>
          </tr>
          <!-- Body Categories -->
          <tr>
            <td style="background:#0d111a; border-left:1px solid #1e3a5f; border-right:1px solid #1e3a5f; padding: 24px 24px 8px 24px;">
              {categories_html}
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="background:#0d111a; border-radius:0 0 16px 16px; padding:20px 32px; text-align:center; border:1px solid #1e3a5f; border-top:none;">
              <p style="color:#64748b; font-size:12px; margin:0 0 8px;">
                Recibís este email porque estás suscripto a las alertas de <strong>Inversiones Picado Fino</strong>.
              </p>
              <a href="{SITE_URL}" style="color:#3b82f6; font-size:12px; text-decoration:none; font-weight:600;">Ver dashboard completo →</a>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def send_daily_alert_email(categorized_assets: dict) -> dict:
    """
    Envía el email del Resumen por Categorías a todos los suscriptores via SMTP.
    Retorna un dict con status, recipient_count y errores.
    """
    subscribers = get_subscribers()
    if not subscribers:
        print("[email_service] No hay suscriptores. Omitiendo envío.")
        return {"status": "no_subscribers", "recipient_count": 0}

    if not ALERT_EMAIL_FROM or not ALERT_EMAIL_PASSWORD:
        print("[email_service] Credenciales SMTP no configuradas.")
        return {"status": "no_credentials", "recipient_count": 0}

    now = datetime.now()
    date_str = now.strftime("%d de %B de %Y")
    subject = f"📈 Resumen de Mercado — {now.strftime('%d %b %Y')} | Inversiones Picado Fino"
    html_body = _build_email_html(categorized_assets, date_str)

    success_count = 0
    errors = []

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(ALERT_EMAIL_SMTP_HOST, int(ALERT_EMAIL_SMTP_PORT)) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(ALERT_EMAIL_FROM, ALERT_EMAIL_PASSWORD)

            for email in subscribers:
                try:
                    msg = MIMEMultipart("alternative")
                    msg["Subject"] = subject
                    msg["From"] = f"Inversiones Picado Fino <{ALERT_EMAIL_FROM}>"
                    msg["To"] = email
                    msg.attach(MIMEText(html_body, "html", "utf-8"))
                    server.sendmail(ALERT_EMAIL_FROM, email, msg.as_string())
                    success_count += 1
                    print(f"[email_service] ✓ Email enviado a {email}")
                except Exception as e:
                    errors.append({"email": email, "error": str(e)})
                    print(f"[email_service] ✗ Error enviando a {email}: {e}")

    except Exception as e:
        print(f"[email_service] Error SMTP: {e}")
        return {"status": "smtp_error", "error": str(e), "recipient_count": 0}

    # Registrar en historial
    log_alert_dispatch(categorized_assets, success_count)

    return {
        "status": "sent",
        "recipient_count": success_count,
        "errors": errors,
    }

