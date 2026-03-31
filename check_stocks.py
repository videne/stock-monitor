import json
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import time
import random

DATA_FILE = "data/history.json"
PRODUCTS_FILE = "data/products.json"

HEADERS_LIST = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ro,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    },
    {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ro-RO,ro;q=0.8,en-US;q=0.5,en;q=0.3",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    },
]

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def check_stock(url):
    for attempt in range(3):
        try:
            headers = random.choice(HEADERS_LIST)
            session = requests.Session()
            # First visit homepage to get cookies
            base_url = "/".join(url.split("/")[:3])
            try:
                session.get(base_url, headers=headers, timeout=10)
                time.sleep(random.uniform(1.5, 3.0))
            except:
                pass

            resp = session.get(url, headers=headers, timeout=20)
            print(f"    HTTP {resp.status_code}")

            if resp.status_code == 403:
                print(f"    Attempt {attempt+1}: blocked (403), retrying...")
                time.sleep(random.uniform(3, 6))
                continue

            if resp.status_code == 404:
                print(f"    Product page not found (404)")
                return "error"

            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # SpringFarma specific: look for availability elements
            for tag in soup.find_all(class_=lambda c: c and any(x in c.lower() for x in [
                "stock", "availability", "disponibil", "stoc", "add-to-cart", "out-of-stock"
            ])):
                tag_text = tag.get_text(strip=True).upper()
                if any(x in tag_text for x in ["INDISPONIBIL", "OUT OF STOCK", "STOC EPUIZAT", "UNAVAILABLE"]):
                    return "nostock"
                if any(x in tag_text for x in ["ÎN STOC", "IN STOC", "IN STOCK", "DISPONIBIL", "ADAUGA IN COS", "ADAUGĂ ÎN COȘ"]):
                    return "stock"

            # Fallback: scan full page text
            full_text = soup.get_text(separator=" ", strip=True).upper()
            if any(x in full_text for x in ["INDISPONIBIL", "OUT OF STOCK", "STOC EPUIZAT"]):
                return "nostock"
            if any(x in full_text for x in ["ÎN STOC", "IN STOC", "IN STOCK", "ADAUGA IN COS"]):
                return "stock"

            return "unknown"

        except requests.exceptions.Timeout:
            print(f"    Attempt {attempt+1}: timeout")
            time.sleep(random.uniform(2, 4))
        except requests.exceptions.ConnectionError as e:
            print(f"    Attempt {attempt+1}: connection error - {e}")
            time.sleep(random.uniform(2, 4))
        except Exception as e:
            print(f"    Attempt {attempt+1}: error - {e}")
            time.sleep(random.uniform(2, 4))

    return "error"

def main():
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
        print(f"  URL: {url}")

        new_status = check_stock(url)

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

        history[pid][today] = {
            "status": new_status,
            "changed": changed,
            "checked_at": datetime.now(timezone.utc).isoformat()
        }

        prod["status"] = new_status
        prod["lastCheck"] = datetime.now(timezone.utc).isoformat()
        if changed:
            prod["lastChanged"] = today

        print(f"  -> {new_status}{' (STATUS CHANGED!)' if changed else ''}")

        # Pause between products to avoid rate limiting
        time.sleep(random.uniform(2, 4))

    save_json(DATA_FILE, history)
    save_json(PRODUCTS_FILE, products)
    print("\nDone. Data saved.")

if __name__ == "__main__":
    main()
