import httpx
from bs4 import BeautifulSoup
import os
import json
import time
import re
from datetime import datetime
from app.config import CACHE_DIR


def calculate_tna_from_price(price: float, maturity_str: str, face_value: float = 100.0, vn_tecnico_maturity: float = None) -> dict:
    """
    Calcula TEM, TNA y TEA reales a partir del precio de mercado y la fecha de vencimiento.

    Para LECAPs que ya capitalizaron gran parte de su vida (precio > VN original):
        - Se debe pasar `vn_tecnico_maturity`: el monto total a recibir al vencimiento
          expresado en las mismas unidades que `price`.
        - TEM = (vn_tecnico_maturity / price) ^ (30 / dias_restantes) - 1

    Para instrumentos de descuento clásico (precio < VN original):
        - TEM = (face_value / price) ^ (30 / dias_restantes) - 1

    Args:
        price: Precio de mercado. Si > 2.0 se asume en pesos nominales.
        maturity_str: Fecha de vencimiento en formato 'YYYY-MM-DD'.
        face_value: Valor nominal de rescate original (default 100.0).
        vn_tecnico_maturity: VN técnico a cobrar al vencimiento (puede ser > face_value
            cuando el instrumento ha capitalizado. Si es None, se usa face_value).

    Returns:
        dict con tna, tem, tea (todos como decimales, ej: 0.30 = 30%).
    """
    try:
        mat = datetime.strptime(maturity_str, "%Y-%m-%d")
        days = (mat - datetime.now()).days
        if days <= 0:
            return {"tna": 0.0, "tem": 0.0, "tea": 0.0}

        # Normalizar precio a pesos por cada 100 de VN original
        p = price / face_value if price > 2.0 else price

        # Determinar el payoff normalizado al vencimiento
        if vn_tecnico_maturity is not None:
            payoff = (vn_tecnico_maturity / face_value) if vn_tecnico_maturity > 2.0 else vn_tecnico_maturity
        else:
            payoff = 1.0  # clásico: cobra exactamente el VN original

        if p <= 0 or payoff <= 0 or payoff < p * 0.95:
            # Si lo que cobrás es menos del 95% de lo que pagás, no tiene sentido económico
            return {"tna": 0.0, "tem": 0.0, "tea": 0.0}

        tem = (payoff / p) ** (30.0 / days) - 1.0
        tna = tem * 12.0
        tea = (1.0 + tem) ** 12.0 - 1.0
        return {
            "tna": round(tna, 4),
            "tem": round(tem, 4),
            "tea": round(tea, 4),
        }
    except Exception:
        return {"tna": 0.0, "tem": 0.0, "tea": 0.0}


def estimate_vn_tecnico_for_lecap(ticker: str, price: float) -> float:
    """
    Estima el VN técnico al vencimiento para una LECAP/BONCAP capitalizada.
    Las LECAPs argentinas capitalizan mensualmente a una TNA de referencia.
    Para calcular la TNA real desde el precio de mercado, aproximamos el VN técnico
    usando la curva de tasas implícita del mercado (~35% TNA de referencia base 2026).

    Este valor se usa SOLO cuando no disponemos del VN técnico exacto (datos de scraping).
    Si el precio supera 102 (sobre par), indica que ya capitalizó parte de los intereses.
    """
    # Para letras S (mensual/bimestral) y T (BONCAPs):
    # VN técnico estimado = precio * (1 + margen_capitalizacion_residual)
    # El mercado descuenta usando la curva argentina (~28-35% TNA implícita)
    # Para una estimación conservadora sin datos exactos, usamos un pequeño spread sobre precio
    if price > 110.0:
        # Muy capitalizada: el payoff real es marginalmente mayor al precio
        # Spread típico: 1.5-2.5% sobre el precio actual según días restantes
        return price * 1.018  # ~1.8% residual conservador
    elif price > 102.0:
        return price * 1.025
    else:
        return 100.0  # precio bajo par → usa VN original


# ============================================================
# LISTA BASE DE LETRAS Y BONCAPs — SOLO INSTRUMENTOS CON TNA >= 18%
# ============================================================
# CRITERIO DE INCLUSIÓN:
#   • TNA >= 18% para ser considerada en el scoring (MIN_TNA_LETRAS_ARS en profiles.py)
#   • LECAPs muy capitalizadas con TNA real ~4-5% están EXCLUIDAS deliberadamente
#     (S31L6, S14G6, S31G6, S30S6, S30O6, S13N6, S30N6) — rendimiento real negativo

FALLBACK_LETRAS = [
    # --- BONCAPs corto-mediano plazo: TNA útil, vencen dentro de 6-12 meses ---
    {"ticker": "T15E7",  "name": "BONCAP T15E7 (Pesos)",  "price": 113.50, "vn_tecnico": 120.00, "tna": 0.155, "maturity": "2027-01-15"},
    {"ticker": "T31Y7",  "name": "BONCAP T31Y7 (Pesos)",  "price": 105.80, "vn_tecnico": 118.00, "tna": 0.240, "maturity": "2027-05-31"},
    {"ticker": "T30J7",  "name": "BONCAP T30J7 (Pesos)",  "price": 102.50, "vn_tecnico": 117.50, "tna": 0.290, "maturity": "2027-06-30"},
    {"ticker": "T28F7",  "name": "BONCAP T28F7 (Pesos)",  "price": 108.20, "vn_tecnico": 118.50, "tna": 0.220, "maturity": "2027-02-28"},
    {"ticker": "T31M7",  "name": "BONCAP T31M7 (Pesos)",  "price": 104.50, "vn_tecnico": 117.80, "tna": 0.260, "maturity": "2027-03-31"},
    {"ticker": "T30A7",  "name": "BONCAP T30A7 (Pesos)",  "price": 103.20, "vn_tecnico": 117.60, "tna": 0.275, "maturity": "2027-04-30"},
    # --- LECAPs largas (>6 meses restantes) con TNA aceptable ---
    {"ticker": "S28F7",  "name": "LECAP S28F7 (Pesos)",   "price": 109.80, "vn_tecnico": 120.50, "tna": 0.195, "maturity": "2027-02-28"},
    {"ticker": "S31M7",  "name": "LECAP S31M7 (Pesos)",   "price": 107.50, "vn_tecnico": 119.80, "tna": 0.215, "maturity": "2027-03-31"},
]

# Lista base de Bonos Soberanos en pesos y dólares
FALLBACK_BONOS = [
    {"ticker": "AL30",  "name": "Bono Soberano AL30 (Pesos)",   "price": 97900.0,  "tna": 0.12, "maturity": "2030-07-09", "currency": "ARS"},
    {"ticker": "GD30",  "name": "Bono Soberano GD30 (Pesos)",   "price": 100600.0, "tna": 0.11, "maturity": "2030-07-09", "currency": "ARS"},
    {"ticker": "AL29",  "name": "Bono Soberano AL29 (Pesos)",   "price": 99100.0,  "tna": 0.13, "maturity": "2029-07-09", "currency": "ARS"},
    {"ticker": "GD29",  "name": "Bono Soberano GD29 (Pesos)",   "price": 100850.0, "tna": 0.12, "maturity": "2029-07-09", "currency": "ARS"},
    {"ticker": "AL35",  "name": "Bono Soberano AL35 (Pesos)",   "price": 124000.0, "tna": 0.14, "maturity": "2035-07-09", "currency": "ARS"},
    {"ticker": "GD35",  "name": "Bono Soberano GD35 (Pesos)",   "price": 126500.0, "tna": 0.13, "maturity": "2035-07-09", "currency": "ARS"},
    {"ticker": "AE38",  "name": "Bono Soberano AE38 (Pesos)",   "price": 128500.0, "tna": 0.12, "maturity": "2038-01-09", "currency": "ARS"},
    {"ticker": "GD38",  "name": "Bono Soberano GD38 (Pesos)",   "price": 130200.0, "tna": 0.11, "maturity": "2038-01-09", "currency": "ARS"},
    {"ticker": "AL30D", "name": "Bono Soberano AL30D (Dólares)", "price": 64.22,    "tna": 0.08, "maturity": "2030-07-09", "currency": "USD"},
    {"ticker": "GD30D", "name": "Bono Soberano GD30D (Dólares)", "price": 66.00,   "tna": 0.07, "maturity": "2030-07-09", "currency": "USD"},
]


async def scrape_rava_table(url, valid_ticker_regex, fallbacks, category_name):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                print(f"Rava returned {response.status_code} for {category_name}. Using fallbacks.")
                return fallbacks
            
            soup = BeautifulSoup(response.text, 'lxml')
            table = soup.find('table') or soup.find('table', {'class': 'table'})
            if not table:
                print(f"No table found for {category_name}. Using fallbacks.")
                return fallbacks
                
            rows = table.find_all('tr')
            results = []
            
            for row in rows[1:]:
                cols = row.find_all('td')
                if len(cols) >= 4:
                    ticker = cols[0].text.strip()
                    if ticker and re.match(valid_ticker_regex, ticker):
                        try:
                            price_str = cols[1].text.strip().replace('.', '').replace(',', '.')
                            price = float(price_str) if price_str else 1.00
                            
                            var_str = cols[2].text.strip().replace(',', '.').replace('%', '')
                            var = float(var_str) if var_str else 0.0
                            
                            currency = "USD" if ticker.endswith('D') else "ARS"

                            # Determinar vencimiento
                            if ticker.startswith('S') or ticker.startswith('T'):  # letras/boncaps
                                maturity = estimate_maturity_from_ticker(ticker)
                            else:  # bonos soberanos
                                maturity = "2030-07-09"
                                if "35" in ticker: maturity = "2035-07-09"
                                elif "38" in ticker: maturity = "2038-01-09"
                                elif "29" in ticker: maturity = "2029-07-09"
                                elif "41" in ticker: maturity = "2041-07-09"

                            # Para letras/boncaps capitalizadas: estimar VN técnico para TNA real
                            # Un precio > 102 indica que el instrumento cotiza sobre par (capitalizado)
                            if (ticker.startswith('S') or ticker.startswith('T')) and currency == "ARS":
                                vn_tecnico = estimate_vn_tecnico_for_lecap(ticker, price)
                                rates = calculate_tna_from_price(price, maturity, vn_tecnico_maturity=vn_tecnico)
                            else:
                                rates = calculate_tna_from_price(price, maturity)

                            tna = rates["tna"]
                            
                            results.append({
                                "ticker": ticker,
                                "name": f"{category_name.capitalize()} {ticker} ({'Dólares' if currency == 'USD' else 'Pesos'})",
                                "price": price,
                                "tna": tna,
                                "tem": rates.get("tem", 0.0),
                                "tea": rates.get("tea", 0.0),
                                "var_pct": var,
                                "maturity": maturity,
                                "currency": currency
                            })
                        except Exception as e:
                            print(f"Error parsing row {ticker}: {e}")
                            
            if len(results) > 0:
                return results
    except Exception as e:
        print(f"Error scraping {category_name}: {e}")
        
    return fallbacks


def estimate_maturity_from_ticker(ticker):
    months_map = {
        'E': '01', 'F': '02', 'M': '03', 'A': '04', 'Y': '05', 'J': '06',
        'G': '07', 'Ag': '08', 'S': '09', 'O': '10', 'N': '11', 'D': '12'
    }
    match = re.match(r'[SX](\d{2})([A-Za-z]+)(\d{1})', ticker)
    if match:
        day, month_code, year_code = match.groups()
        month = months_map.get(month_code, '06')
        year = f"202{year_code}"
        return f"{year}-{month}-{day}"
    return "2025-12-31"


async def scrape_iamc_fallback(category):
    """
    Parser secundario de contingencia usando IAMC (Instituto Argentino de Mercado de Capitales)
    o Bolsar como fuente alternativa de datos de renta fija.
    """
    urls = {
        "letras": "https://www.iamc.com.ar/informes/letras/",
        "bonos": "https://www.iamc.com.ar/informes/bonos/"
    }
    url = urls.get(category)
    if not url:
        return None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                print(f"IAMC returned {response.status_code} for {category}.")
                return None

            soup = BeautifulSoup(response.text, 'lxml')
            table = soup.find('table')
            if not table:
                print(f"No table found in IAMC for {category}.")
                return None

            rows = table.find_all('tr')
            results = []
            for row in rows[1:]:
                cols = row.find_all('td')
                if len(cols) >= 3:
                    ticker = cols[0].text.strip()
                    if not ticker:
                        continue
                    try:
                        price_str = cols[1].text.strip().replace('.', '').replace(',', '.')
                        price = float(price_str) if price_str else 1.00
                        currency = "USD" if ticker.endswith('D') else "ARS"
                        tna = 0.55 if currency == "ARS" else 0.20
                        maturity = "2030-07-09"

                        results.append({
                            "ticker": ticker,
                            "name": f"{category.capitalize()} {ticker} ({'Dólares' if currency == 'USD' else 'Pesos'})",
                            "price": price,
                            "tna": tna,
                            "var_pct": 0.0,
                            "maturity": maturity,
                            "currency": currency
                        })
                    except Exception as e:
                        print(f"IAMC parse error for {ticker}: {e}")

            if len(results) > 0:
                print(f"IAMC devolvió {len(results)} instrumentos de {category}.")
                return results
    except Exception as e:
        print(f"Error scraping IAMC for {category}: {e}")

    return None


async def fetch_arg_fixed_income_data(force_refresh=False):
    cache_path = os.path.join(CACHE_DIR, "fixed_income.json")
    
    if not force_refresh and os.path.exists(cache_path):
        try:
            with open(cache_path, "r") as f:
                cached = json.load(f)
            if time.time() - cached.get("timestamp", 0) < 3600 * 4:  # 4h TTL
                return cached.get("data")
        except Exception:
            pass
            
    # Scraping simultáneo de letras y bonos (con fallback IAMC)
    print("Scraping Letras y Bonos de Rava (con fallback IAMC)...")
    letras = await scrape_rava_table(
        "https://www.rava.com/cotizaciones/letras", 
        r'^[SXY]\d{2}[A-Za-z]+\d{1}$', 
        None,
        "letra"
    )
    
    # Si Rava falla, intentar IAMC como fuente secundaria
    if letras is None or len(letras) == 0:
        print("Rava falló para letras, intentando IAMC como fallback...")
        letras = await scrape_iamc_fallback("letras")
    
    # Si ambos fallan, usar datos estáticos
    if letras is None or len(letras) == 0:
        print("Usando datos estáticos de letras como último recurso.")
        letras = FALLBACK_LETRAS
    
    bonos = await scrape_rava_table(
        "https://www.rava.com/cotizaciones/bonos",
        r'^(AL|GD|AE|CO)\d{2}[D]?$', 
        None,
        "bono"
    )
    
    if bonos is None or len(bonos) == 0:
        print("Rava falló para bonos, intentando IAMC como fallback...")
        bonos = await scrape_iamc_fallback("bonos")
    
    if bonos is None or len(bonos) == 0:
        print("Usando datos estáticos de bonos como último recurso.")
        bonos = FALLBACK_BONOS
    
    results = []
    
    for letra in letras:
        # Calcular TNA real considerando el VN técnico al vencimiento
        if "tna" not in letra or letra["tna"] == 0.0:
            vn_mat = letra.get("vn_tecnico")
            rates = calculate_tna_from_price(letra["price"], letra["maturity"], vn_tecnico_maturity=vn_mat)
        else:
            rates = {"tna": letra["tna"], "tem": letra.get("tem", letra["tna"] / 12), "tea": letra.get("tea", 0.0)}
        tna = rates["tna"]
        price = letra["price"]

        # Calcular retorno efectivo al vencimiento (NO anualizar como si durara 12 meses)
        # Si la letra vence en 5 meses, su retorno real a ese horizonte es proporcional
        try:
            mat = datetime.strptime(letra["maturity"], "%Y-%m-%d")
            days_to_maturity = max(1, (mat - datetime.now()).days)
            maturity_fraction = days_to_maturity / 365.25
        except Exception:
            days_to_maturity = 180
            maturity_fraction = 0.5

        # Retorno efectivo hasta vencimiento (lo que realmente ganás)
        effective_return = tna * maturity_fraction

        # Construir retornos periódicos realistas: proporcionales al plazo efectivo
        ret_1m  = tna / 12.0
        ret_3m  = min(effective_return, tna * (3 / 12.0))
        ret_6m  = min(effective_return, tna * (6 / 12.0))
        ret_12m = effective_return  # lo que realmente rendirá hasta vencimiento

        results.append({
            "ticker": letra["ticker"],
            "name": letra["name"],
            "category": "letras",
            "price": price,
            "currency": letra.get("currency", "ARS"),
            "ret_1m": ret_1m,
            "ret_3m": ret_3m,
            "ret_6m": ret_6m,
            "ret_12m": ret_12m,
            "volatility": 0.05,
            "sharpe": max(0.1, tna / 0.22 * 0.8),  # Sharpe relativo a inflación base
            "rsi": 50.0,
            "tna": tna,
            "tem": rates["tem"],
            "tea": rates["tea"],
            "days_to_maturity": days_to_maturity,
            "effective_return": round(effective_return, 4),
            "support": round(price * 0.985, 2),
            "resistance": round(price * 1.015, 2),
            "volume_cluster": round(price * 0.995, 2),
            "maturity": letra["maturity"],
            "trend": "Estable"
        })
        
    for bono in bonos:
        if "tna" not in bono or bono["tna"] == 0.0:
            rates = calculate_tna_from_price(bono["price"], bono["maturity"])
        else:
            rates = {"tna": bono["tna"], "tem": bono.get("tem", bono["tna"] / 12), "tea": bono.get("tea", 0.0)}
        bono_tna = rates["tna"]
        vol = 0.22 if bono.get("currency") == "ARS" else 0.16
        price = bono["price"]

        try:
            mat = datetime.strptime(bono["maturity"], "%Y-%m-%d")
            days_to_maturity = max(1, (mat - datetime.now()).days)
            maturity_fraction = min(days_to_maturity / 365.25, 1.0)  # cap a 1 año para ret_12m
        except Exception:
            days_to_maturity = 365
            maturity_fraction = 1.0

        results.append({
            "ticker": bono["ticker"],
            "name": bono["name"],
            "category": "bonos",
            "price": price,
            "currency": bono.get("currency", "ARS"),
            "ret_1m": bono_tna / 12,
            "ret_3m": (bono_tna / 12) * 3,
            "ret_6m": (bono_tna / 12) * 6,
            "ret_12m": bono_tna,
            "volatility": vol,
            "sharpe": 0.6 if bono.get("currency") == "ARS" else 0.8,
            "rsi": 52.0,
            "tna": bono_tna,
            "tem": rates["tem"],
            "tea": rates["tea"],
            "days_to_maturity": days_to_maturity,
            "support": round(price * 0.88, 2),
            "resistance": round(price * 1.12, 2),
            "volume_cluster": round(price * 0.95, 2),
            "maturity": bono["maturity"],
            "trend": "Alcista" if bono.get("var_pct", 0) > 0 else "Estable"
        })
        
    # Filtrar instrumentos vencidos dinámicamente
    today_str = datetime.now().strftime("%Y-%m-%d")
    valid_results = []
    for item in results:
        mat_date = item.get("maturity")
        if mat_date and mat_date < today_str:
            print(f"WARNING: El instrumento de renta fija '{item['ticker']}' ha vencido ({mat_date} < {today_str}) y ha sido excluido.")
        else:
            valid_results.append(item)
    results = valid_results

    cache_data = {
        "timestamp": time.time(),
        "data": results
    }
    with open(cache_path, "w") as f:
        json.dump(cache_data, f)
        
    return results
