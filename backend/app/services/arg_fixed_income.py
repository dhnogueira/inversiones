import httpx
from bs4 import BeautifulSoup
import os
import json
import time
import re
from app.config import CACHE_DIR

# Lista base de Letras (LECAPs/LECERs) en caso de que falle el scraping
FALLBACK_LETRAS = [
    {"ticker": "S28F5", "name": "Letra de Tesoro S28F5 (Pesos)", "price": 1.02, "tna": 0.442, "maturity": "2025-02-28"},
    {"ticker": "S31A5", "name": "Letra de Tesoro S31A5 (Pesos)", "price": 0.98, "tna": 0.458, "maturity": "2025-04-30"},
    {"ticker": "S30J5", "name": "Letra de Tesoro S30J5 (Pesos)", "price": 0.95, "tna": 0.465, "maturity": "2025-06-30"},
    {"ticker": "S30S5", "name": "Letra de Tesoro S30S5 (Pesos)", "price": 0.90, "tna": 0.480, "maturity": "2025-09-30"},
    {"ticker": "S15D5", "name": "Letra de Tesoro S15D5 (Pesos)", "price": 0.86, "tna": 0.495, "maturity": "2025-12-15"},
    {"ticker": "S31M5", "name": "Letra de Tesoro S31M5 (Pesos)", "price": 1.01, "tna": 0.450, "maturity": "2025-03-31"},
    {"ticker": "S31Y5", "name": "Letra de Tesoro S31Y5 (Pesos)", "price": 0.97, "tna": 0.461, "maturity": "2025-05-31"},
    {"ticker": "S29G5", "name": "Letra de Tesoro S29G5 (Pesos)", "price": 0.93, "tna": 0.472, "maturity": "2025-07-29"},
    {"ticker": "S29Ag5", "name": "Letra de Tesoro S29Ag5 (Pesos)", "price": 0.91, "tna": 0.477, "maturity": "2025-08-29"},
    {"ticker": "S31O5", "name": "Letra de Tesoro S31O5 (Pesos)", "price": 0.88, "tna": 0.485, "maturity": "2025-10-31"}
]

# Lista base de Bonos Soberanos en pesos y dólares
FALLBACK_BONOS = [
    {"ticker": "AL30", "name": "Bono Soberano AL30 (Pesos)", "price": 61200.0, "tna": 0.58, "maturity": "2030-07-09", "currency": "ARS"},
    {"ticker": "GD30", "name": "Bono Soberano GD30 (Pesos)", "price": 64500.0, "tna": 0.55, "maturity": "2030-07-09", "currency": "ARS"},
    {"ticker": "AL29", "name": "Bono Soberano AL29 (Pesos)", "price": 62100.0, "tna": 0.60, "maturity": "2029-07-09", "currency": "ARS"},
    {"ticker": "GD29", "name": "Bono Soberano GD29 (Pesos)", "price": 65000.0, "tna": 0.57, "maturity": "2029-07-09", "currency": "ARS"},
    {"ticker": "AL35", "name": "Bono Soberano AL35 (Pesos)", "price": 49800.0, "tna": 0.62, "maturity": "2035-07-09", "currency": "ARS"},
    {"ticker": "GD35", "name": "Bono Soberano GD35 (Pesos)", "price": 51200.0, "tna": 0.59, "maturity": "2035-07-09", "currency": "ARS"},
    {"ticker": "AE38", "name": "Bono Soberano AE38 (Pesos)", "price": 54200.0, "tna": 0.56, "maturity": "2038-01-09", "currency": "ARS"},
    {"ticker": "GD38", "name": "Bono Soberano GD38 (Pesos)", "price": 59300.0, "tna": 0.53, "maturity": "2038-01-09", "currency": "ARS"},
    {"ticker": "AL30D", "name": "Bono Soberano AL30D (Dólares)", "price": 61.20, "tna": 0.22, "maturity": "2030-07-09", "currency": "USD"},
    {"ticker": "GD30D", "name": "Bono Soberano GD30D (Dólares)", "price": 64.50, "tna": 0.20, "maturity": "2030-07-09", "currency": "USD"}
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
                            
                            # Cargar valores específicos basado en ticker
                            # Si es bono, estimar TNA acorde al tipo de bono
                            tna = 0.55 if currency == "ARS" else 0.20
                            if ticker.startswith('S'): # letras
                                tna = 0.44 + (0.01 * (len(ticker) % 6))
                                maturity = estimate_maturity_from_ticker(ticker)
                            else: # bonos
                                maturity = "2030-07-09"
                                if "35" in ticker: maturity = "2035-07-09"
                                elif "38" in ticker: maturity = "2038-01-09"
                                elif "29" in ticker: maturity = "2029-07-09"
                                elif "41" in ticker: maturity = "2041-07-09"
                            
                            results.append({
                                "ticker": ticker,
                                "name": f"{category_name.capitalize()} {ticker} ({'Dólares' if currency == 'USD' else 'Pesos'})",
                                "price": price,
                                "tna": tna,
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
        results.append({
            "ticker": letra["ticker"],
            "name": letra["name"],
            "category": "letras",
            "price": letra["price"],
            "currency": letra.get("currency", "ARS"),
            "ret_1m": letra["tna"] / 12,
            "ret_3m": (letra["tna"] / 12) * 3,
            "ret_6m": (letra["tna"] / 12) * 6,
            "ret_12m": letra["tna"],
            "volatility": 0.05,
            "sharpe": 1.5,
            "rsi": 50.0,
            "tna": letra["tna"],
            "maturity": letra["maturity"],
            "trend": "Estable"
        })
        
    for bono in bonos:
        # Los bonos soberanos argentinos tienen una volatilidad media del 18%-28% anual en pesos
        vol = 0.22 if bono.get("currency") == "ARS" else 0.16
        results.append({
            "ticker": bono["ticker"],
            "name": bono["name"],
            "category": "bonos",
            "price": bono["price"],
            "currency": bono.get("currency", "ARS"),
            "ret_1m": bono["tna"] / 12,
            "ret_3m": (bono["tna"] / 12) * 3,
            "ret_6m": (bono["tna"] / 12) * 6,
            "ret_12m": bono["tna"],
            "volatility": vol,
            "sharpe": 0.6 if bono.get("currency") == "ARS" else 0.8,
            "rsi": 52.0,
            "tna": bono["tna"],
            "maturity": bono["maturity"],
            "trend": "Alcista" if bono.get("var_pct", 0) > 0 else "Estable"
        })
        
    cache_data = {
        "timestamp": time.time(),
        "data": results
    }
    with open(cache_path, "w") as f:
        json.dump(cache_data, f)
        
    return results
