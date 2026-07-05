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


# ──────────────────────────────────────────────────────────────────────────────
# Gestión de suscriptores
# ──────────────────────────────────────────────────────────────────────────────

def get_subscribers() -> list[str]:
    """Retorna la lista de emails suscriptos."""
    if not os.path.exists(SUBSCRIBERS_FILE):
        return []
    try:
        with open(SUBSCRIBERS_FILE, "r") as f:
            return json.load(f).get("emails", [])
    except Exception as e:
        print(f"[email_service] Error leyendo suscriptores: {e}")
        return []


def add_subscriber(email: str) -> dict:
    """Agrega un email a la lista. Ignora duplicados."""
    email = email.strip().lower()
    subscribers = get_subscribers()
    if email in subscribers:
        return {"status": "already_subscribed", "email": email}
    subscribers.append(email)
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump({"emails": subscribers}, f, indent=2)
    return {"status": "subscribed", "email": email}


def remove_subscriber(email: str) -> dict:
    """Elimina un email de la lista."""
    email = email.strip().lower()
    subscribers = get_subscribers()
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


# ──────────────────────────────────────────────────────────────────────────────
# Template HTML del email
# ──────────────────────────────────────────────────────────────────────────────

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


def _build_email_html(top5: list, date_str: str) -> str:
    assets_html = ""
    for i, asset in enumerate(top5, 1):
        ticker = asset.get("ticker", "")
        name = asset.get("name", ticker)
        score = asset.get("score", 0)
        category = asset.get("category", "")
        price = asset.get("price", 0)
        summary = _build_asset_summary(asset)
        cat_label = CATEGORY_LABELS.get(category, category.upper())
        cat_color = CATEGORY_COLORS.get(category, "#64748b")
        modal_url = f"{SITE_URL}#modal={ticker}"

        assets_html += f"""
        <tr>
          <td style="padding: 18px 24px; border-bottom: 1px solid #1e2d3e;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td>
                  <span style="font-size:13px; font-weight:700; color:#fff; background:{cat_color}; padding:3px 9px; border-radius:20px; display:inline-block; margin-bottom:6px;">{cat_label}</span>
                  <div style="font-size:22px; font-weight:800; color:#fff; letter-spacing:-0.5px;">
                    #{i} {ticker} <span style="font-size:14px; color:#94a3b8; font-weight:400;">{name}</span>
                  </div>
                  <div style="font-size:13px; color:#94a3b8; margin-top:4px;">{summary}</div>
                </td>
                <td style="text-align:right; vertical-align:top; white-space:nowrap; padding-left:12px;">
                  <div style="font-size:18px; font-weight:700; color:#10b981;">${price:,.2f}</div>
                  <div style="font-size:12px; color:#64748b;">Score: {score:.1f}</div>
                  <a href="{modal_url}" style="display:inline-block; margin-top:8px; background:#3b82f6; color:#fff; text-decoration:none; font-size:12px; font-weight:600; padding:6px 14px; border-radius:8px;">Ver análisis →</a>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        """

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>📈 Top 5 del día — Inversiones Picado Fino</title>
</head>
<body style="margin:0; padding:0; background:#0d111a; font-family:'Segoe UI', Arial, sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:32px 16px;">
    <tr>
      <td align="center">
        <!-- Header -->
        <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px; width:100%;">
          <tr>
            <td style="background: linear-gradient(135deg, #1e2d3e 0%, #0d111a 100%); border-radius:16px 16px 0 0; padding:28px 32px; text-align:center; border:1px solid #1e3a5f; border-bottom:none;">
              <div style="font-size:13px; color:#64748b; margin-bottom:6px; text-transform:uppercase; letter-spacing:2px;">Inversiones Picado Fino 🥩</div>
              <div style="font-size:26px; font-weight:800; color:#fff;">📈 Top 5 del día</div>
              <div style="font-size:14px; color:#94a3b8; margin-top:6px;">{date_str}</div>
            </td>
          </tr>
          <!-- Asset cards -->
          <tr>
            <td style="background:#111827; border:1px solid #1e3a5f; border-top:none; border-bottom:none;">
              <table width="100%" cellpadding="0" cellspacing="0">
                {assets_html}
              </table>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="background:#0d111a; border-radius:0 0 16px 16px; padding:20px 32px; text-align:center; border:1px solid #1e3a5f; border-top:none;">
              <p style="color:#64748b; font-size:12px; margin:0 0 8px;">
                Recibís este email porque estás suscripto a <strong>Inversiones Picado Fino</strong>.
              </p>
              <a href="{SITE_URL}" style="color:#3b82f6; font-size:12px;">Ver dashboard completo →</a>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


# ──────────────────────────────────────────────────────────────────────────────
# Envío de email SMTP
# ──────────────────────────────────────────────────────────────────────────────

def send_daily_alert_email(top5: list) -> dict:
    """
    Envía el email de Top 5 a todos los suscriptores via SMTP.
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
    subject = f"📈 Top 5 del día — {now.strftime('%d %b %Y')} | Inversiones Picado Fino"
    html_body = _build_email_html(top5, date_str)

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
    log_alert_dispatch(top5, success_count)

    return {
        "status": "sent",
        "recipient_count": success_count,
        "errors": errors,
    }
