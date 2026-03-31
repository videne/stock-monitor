import json
import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import time
import random

DATA_FILE = "data/history.json"
PRODUCTS_FILE = "data/products.json"
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "")

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def extract_price(soup):
    """Extrage prețul din pagina produsului."""
    # Caută elemente cu clase CSS specifice pentru preț
    price_classes = ["price", "pret", "product-price", "amount", "woocommerce-Price-amount",
                     "price-box", "regular-price", "special-price", "final-price"]
    for cls in price_classes:
        tag = soup.find(class_=lambda c: c and cls in c.lower())
        if tag:
            text = tag.get_text(strip=True)
            # Extrage numărul (ex: "45,99 lei" → "45.99")
            match = re.search(r'(\d+[.,]\d+|\d+)', text.replace('.', '').replace(',', '.'))
            if match:
                price = match.group(1)
                print(f"    -> Preț găsit ({cls}): {price} lei")
                return price

    # Fallback: caută în tot textul paginii
    full_text = soup.get_text(separator=" ", strip=True)
    match = re.search(r'(\d+[.,]\d+)\s*(?:lei|RON)', full_text)
    if match:
        price = match.group(1).replace(',', '.')
        print(f"    -> Preț găsit (text pagină): {price} lei")
        return price

    print(f"    -> Preț negăsit")
    return None

def check_stock(url):
    for attempt in range(3):
        try:
            scraper_url = f"http://api.scraperapi.com?api_key={SCRAPER_API_KEY}&url={url}&country_code=ro"
            resp = requests.get(scraper_url, timeout=60)
            print(f"    HTTP {resp.status_code}")

            if resp.status_code == 403:
                print(f"    Attempt {attempt+1}: blocked, retrying...")
                time.sleep(random.uniform(3, 6))
                continue

            if resp.status_code == 404:
                print(f"    Product page not found (404)")
                return "error", None

            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Extrage prețul
            price = extract_price(soup)

            # Dacă nu avem preț, tratăm produsul ca FĂRĂ STOC.
            # Pe site-urile urmărite, lipsa prețului indică de obicei indisponibilitate.
            if price is None:
                print(f"    -> Preț negăsit: tratăm produsul ca FĂRĂ STOC")
                return "nostock", None

            # 1. Verificare buton "Adaugă în coș" — cel mai fiabil indicator de stoc
            add_to_cart = soup.find(lambda tag: (
                tag.name in ["button", "a", "input", "span", "div"]
                and "ADAUG" in tag.get_text(strip=True).upper()
                and "CO" in tag.get_text(strip=True).upper()
            ))
            if add_to_cart:
                print(f"    -> Buton 'Adaugă în coș' găsit: ÎN STOC")
                return "stock", price

            # 2. Verificare clase CSS specifice
            for tag in soup.find_all(class_=lambda c: c and any(x in c.lower() for x in [
                "stock", "availability", "disponibil", "stoc", "add-to-cart", "out-of-stock",
                "unavailable", "indisponibil"
            ])):
                tag_text = tag.get_text(strip=True).upper()
                if any(x in tag_text for x in ["INDISPONIBIL", "OUT OF STOCK", "STOC EPUIZAT", "EPUIZAT"]):
                    print(f"    -> Text indisponibil în clasă CSS: FĂRĂ STOC")
                    return "nostock", price
                if any(x in tag_text for x in ["ÎN STOC", "IN STOC", "IN STOCK", "DISPONIBIL"]):
                    print(f"    -> Text în stoc în clasă CSS: ÎN STOC")
                    return "stock", price

            # 3. Scanare text complet — INDISPONIBIL are prioritate față de ÎN STOC
            full_text = soup.get_text(separator=" ", strip=True).upper()
            if any(x in full_text for x in ["INDISPONIBIL", "OUT OF STOCK", "STOC EPUIZAT", "EPUIZAT"]):
                print(f"    -> Text indisponibil în pagină: FĂRĂ STOC")
                return "nostock", price
            if any(x in full_text for x in ["ÎN STOC", "IN STOC", "IN STOCK"]):
                print(f"    -> Text în stoc în pagină: ÎN STOC")
                return "stock", price

            return "unknown", price

        except requests.exceptions.Timeout:
            print(f"    Attempt {attempt+1}: timeout")
            time.sleep(random.uniform(2, 4))
        except Exception as e:
            print(f"    Attempt {attempt+1}: error - {e}")
            time.sleep(random.uniform(2, 4))

    return "error", None

def main():
    if not SCRAPER_API_KEY:
        print("ERROR: SCRAPER_API_KEY not set!")
        return

    products = load_json(PRODUCTS_FILE, [])
    history = load_json(DATA_FILE, {})

    if not products:
        print("No products found in data/products.json")
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"Checking {len(products)} products for {today}...")

    for prod in products:
        pid = prod["id"]
        url = prod["url"]
        print(f"\n  Checking: {prod.get('name', url)}")

        new_status, new_price = check_stock(url)

        if pid not in history:
            history[pid] = {}

        prev_dates = sorted(history[pid].keys())
        prev_status = None
        if prev_dates:
            last = prev_dates[-1]
            if last != today:
                prev_status = history[pid][last].get("status")

        changed = (
            prev_status is not None
            and prev_status not in ("unknown", "error")
            and prev_status != new_status
            and new_status not in ("unknown", "error")
        )

        # Salvează și modificarea de preț în istoric
        prev_price = prod.get("price")
        price_changed = (new_price is not None and prev_price is not None and new_price != prev_price)

        history[pid][today] = {
            "status": new_status,
            "changed": changed,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "price": new_price,
            "price_changed": price_changed
        }

        prod["status"] = new_status
        prod["lastCheck"] = datetime.now(timezone.utc).isoformat()
        if new_price is not None:
            prod["price"] = new_price
        if changed:
            prod["lastChanged"] = today

        status_log = f"  -> {new_status}{' (STATUS CHANGED!)' if changed else ''}"
        price_log = f" | pret: {new_price} lei{' (PRET SCHIMBAT! era ' + str(prev_price) + ' lei)' if price_changed else ''}" if new_price else ""
        print(status_log + price_log)
        time.sleep(random.uniform(1, 2))

    save_json(DATA_FILE, history)
    save_json(PRODUCTS_FILE, products)
    print("\nDone. Data saved.")

if __name__ == "__main__":
    main()
