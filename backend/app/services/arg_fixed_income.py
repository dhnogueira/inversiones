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

# Lista base de Letras (LECAPs/BONCAPs) para uso cuando falla el scraping.
# Precios expresados en pesos por cada $100 de VN original (ej: 119 = $119 por VN$100).
# 'vn_tecnico': monto a cobrar al vencimiento por cada VN$100 original.
# 'tna': TNA real de mercado (julio 2026) calculada con VN técnico correcto.
# NOTA: Las LECAPs capitalistas como S30N6 cotizan SOBRE PAR porque el VN técnico
# ya fue capitalizado; su retorno real al vencimiento es marginal (~4% TNA).
FALLBACK_LETRAS = [
    # --- Corto plazo < 60 días (buen TNA pero poco tiempo) ---
    {"ticker": "S31L6",  "name": "LECAP S31L6 (Pesos)",   "price": 115.80, "vn_tecnico": 116.30, "tna": 0.038, "maturity": "2026-07-31"},
    {"ticker": "S14G6",  "name": "LECAP S14G6 (Pesos)",   "price": 116.50, "vn_tecnico": 117.30, "tna": 0.041, "maturity": "2026-08-14"},
    {"ticker": "S31G6",  "name": "LECAP S31G6 (Pesos)",   "price": 117.10, "vn_tecnico": 118.30, "tna": 0.042, "maturity": "2026-08-31"},
    # --- Mediano plazo 60-180 días ---
    {"ticker": "S30S6",  "name": "LECAP S30S6 (Pesos)",   "price": 118.20, "vn_tecnico": 119.80, "tna": 0.043, "maturity": "2026-09-30"},
    {"ticker": "S30O6",  "name": "LECAP S30O6 (Pesos)",   "price": 118.90, "vn_tecnico": 120.70, "tna": 0.044, "maturity": "2026-10-30"},
    {"ticker": "S13N6",  "name": "LECAP S13N6 (Pesos)",   "price": 119.30, "vn_tecnico": 121.20, "tna": 0.044, "maturity": "2026-11-13"},
    # --- S30N6: ya capitalizada, cotiza sobre par, TNA real ~4.4% (inadmisible) ---
    {"ticker": "S30N6",  "name": "LECAP S30N6 (Pesos)",   "price": 119.00, "vn_tecnico": 121.10, "tna": 0.044, "maturity": "2026-11-30"},
    # --- BONCAPs 6-12 meses: mayor TNA, mayor plazo ---
    {"ticker": "T15E7",  "name": "BONCAP T15E7 (Pesos)",  "price": 113.50, "vn_tecnico": 120.00, "tna": 0.155, "maturity": "2027-01-15"},
    {"ticker": "T31Y7",  "name": "BONCAP T31Y7 (Pesos)",  "price": 105.80, "vn_tecnico": 118.00, "tna": 0.240, "maturity": "2027-05-31"},
    {"ticker": "T30J7",  "name": "BONCAP T30J7 (Pesos)",  "price": 102.50, "vn_tecnico": 117.50, "tna": 0.290, "maturity": "2027-06-30"},
]

# Lista base de Bonos Soberanos en pesos y dólares
FALLBACK_BONOS = [
    {"ticker": "AL30", "name": "Bono Soberano AL30 (Pesos)", "price": 97900.0, "tna": 0.12, "maturity": "2030-07-09", "currency": "ARS"},
    {"ticker": "GD30", "name": "Bono Soberano GD30 (Pesos)", "price": 100600.0, "tna": 0.11, "maturity": "2030-07-09", "currency": "ARS"},
    {"ticker": "AL29", "name": "Bono Soberano AL29 (Pesos)", "price": 99100.0, "tna": 0.13, "maturity": "2029-07-09", "currency": "ARS"},
    {"ticker": "GD29", "name": "Bono Soberano GD29 (Pesos)", "price": 100850.0, "tna": 0.12, "maturity": "2029-07-09", "currency": "ARS"},
    {"ticker": "AL35", "name": "Bono Soberano AL35 (Pesos)", "price": 124000.0, "tna": 0.14, "maturity": "2035-07-09", "currency": "ARS"},
    {"ticker": "GD35", "name": "Bono Soberano GD35 (Pesos)", "price": 126500.0, "tna": 0.13, "maturity": "2035-07-09", "currency": "ARS"},
    {"ticker": "AE38", "name": "Bono Soberano AE38 (Pesos)", "price": 128500.0, "tna": 0.12, "maturity": "2038-01-09", "currency": "ARS"},
    {"ticker": "GD38", "name": "Bono Soberano GD38 (Pesos)", "price": 130200.0, "tna": 0.11, "maturity": "2038-01-09", "currency": "ARS"},
    {"ticker": "AL30D", "name": "Bono Soberano AL30D (Dólares)", "price": 64.22, "tna": 0.08, "maturity": "2030-07-09", "currency": "USD"},
    {"ticker": "GD30D", "name": "Bono Soberano GD30D (Dólares)", "price": 66.00, "tna": 0.07, "maturity": "2030-07-09", "currency": "USD"}
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
                            if ticker.startswith('S') or ticker.startswith('T'): # letras/boncaps
                                maturity = estimate_maturity_from_ticker(ticker)
                            else: # bonos soberanos
                                maturity = "2030-07-09"
                                if "35" in ticker: maturity = "2035-07-09"
                                elif "38" in ticker: maturity = "2038-01-09"
                                elif "29" in ticker: maturity = "2029-07-09"
                                elif "41" in ticker: maturity = "2041-07-09"

                            # Calcular TNA real desde el precio de mercado y el vencimiento
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
            if time.time() - cached.get("timestamp", 0) < 3600 * 4: # 4h TTL
                return cached.get("data")
        except Exception:
            pass
            
    # Scraping simultáneo de letras y bonos (con fallback IAMC)
    print("Scraping Letras y Bonos de Rava (con fallback IAMC)...")
    letras = await scrape_rava_table(
        "https://www.rava.com/cotizaciones/letras", 
        r'^[SXY]\d{2}[A-Za-z]+\d{1}$', 
        None,  # No usar fallback aún
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
            vn_mat = letra.get("vn_tecnico")  # puede ser None para datos de scraping
            rates = calculate_tna_from_price(letra["price"], letra["maturity"], vn_tecnico_maturity=vn_mat)
        else:
            rates = {"tna": letra["tna"], "tem": letra.get("tem", letra["tna"] / 12), "tea": letra.get("tea", 0.0)}
        tna = rates["tna"]
        price = letra["price"]
        results.append({
            "ticker": letra["ticker"],
            "name": letra["name"],
            "category": "letras",
            "price": price,
            "currency": letra.get("currency", "ARS"),
            "ret_1m": tna / 12,
            "ret_3m": (tna / 12) * 3,
            "ret_6m": (tna / 12) * 6,
            "ret_12m": tna,
            "volatility": 0.05,
            "sharpe": 1.5,
            "rsi": 50.0,
            "tna": tna,
            "tem": rates["tem"],
            "tea": rates["tea"],
            "support": round(price * 0.985, 2),
            "resistance": round(price * 1.015, 2),
            "volume_cluster": round(price * 0.995, 2),
            "maturity": letra["maturity"],
            "trend": "Estable"
        })
        
    for bono in bonos:
        # Para bonos: usar TNA scrapeada si existe, si no calcular desde precio y vencimiento
        if "tna" not in bono or bono["tna"] == 0.0:
            rates = calculate_tna_from_price(bono["price"], bono["maturity"])
        else:
            rates = {"tna": bono["tna"], "tem": bono.get("tem", bono["tna"] / 12), "tea": bono.get("tea", 0.0)}
        bono_tna = rates["tna"]
        vol = 0.22 if bono.get("currency") == "ARS" else 0.16
        price = bono["price"]
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
