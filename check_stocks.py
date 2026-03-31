import json
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

DATA_FILE = "data/history.json"
PRODUCTS_FILE = "data/products.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

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
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(separator=" ", strip=True).upper()
        for tag in soup.find_all(class_=lambda c: c and any(x in c.lower() for x in ["stock", "availability", "disponibil"])):
            tag_text = tag.get_text(strip=True).upper()
            if "INDISPONIBIL" in tag_text or "OUT OF STOCK" in tag_text:
                return "nostock"
            if "ÎN STOC" in tag_text or "IN STOC" in tag_text or "IN STOCK" in tag_text:
                return "stock"
        if "INDISPONIBIL" in text or "OUT OF STOCK" in text:
            return "nostock"
        if "ÎN STOC" in text or "IN STOC" in text or "IN STOCK" in text:
            return "stock"
        return "unknown"
    except Exception as e:
        print(f"  Error checking {url}: {e}")
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
        print(f"  Checking: {prod.get('name', url)}")
        new_status = check_stock(url)
        if pid not in history:
            history[pid] = {}
        prev_dates = sorted(history[pid].keys())
        prev_status = None
        if prev_dates:
            last = prev_dates[-1]
            if last != today:
                prev_status = history[pid][last].get("status")
        changed = prev_status is not None and prev_status not in ("unknown", "error") and prev_status != new_status
        history[pid][today] = {
            "status": new_status,
            "changed": changed,
            "checked_at": datetime.now(timezone.utc).isoformat()
        }
        prod["status"] = new_status
        prod["lastCheck"] = datetime.now(timezone.utc).isoformat()
        if changed:
            prod["lastChanged"] = today
        print(f"    -> {new_status}{' (CHANGED!)' if changed else ''}")
    save_json(DATA_FILE, history)
    save_json(PRODUCTS_FILE, products)
    print("Done. Data saved.")

if __name__ == "__main__":
    main()
