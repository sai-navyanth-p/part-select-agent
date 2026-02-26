"""PartSelect web scraper using Playwright with stealth mode.

Scrapes product pages and model compatibility data from partselect.com.
Outputs JSON to data/scraped/.

Usage:
    cd backend
    source venv/bin/activate
    PYTHONPATH=. python -m scraper.scraper
"""

import os
import json
import time
import random
import re
from bs4 import BeautifulSoup
from tqdm import tqdm

BASE_URL = "https://www.partselect.com"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "scraped")

TARGET_MODELS = [
    "WDT780SAEM1", "WRS325SDHZ", "WRS588FIHZ", "WRF555SDFZ",
    "WRF535SWHZ", "WRT318FZDW", "WDF520PADM7", "WDT720PADM2",
    "WDTA50SAHZ0", "WDT750SAHZ0", "KDTM354DSS5",
    "RF28HMEDBSR", "GSS25GSHSS", "LFXS26973S", "FFSS2615TS",
    "DW80R5060US", "GDT695SSJSS", "LDF5545SS",
    "MDB4949SHZ0", "WDF550SAAS0",
]

DIRECT_PRODUCT_URLS = [
    ("https://www.partselect.com/PS11752778-Whirlpool-WPW10321304-Door-Shelf-Bin.htm", "refrigerator"),
    ("https://www.partselect.com/PS11750089-Whirlpool-WPW10300022-Refrigerator-Ice-Maker-Assembly.htm", "refrigerator"),
    ("https://www.partselect.com/PS11757023-Whirlpool-W10295370A-Refrigerator-Water-Filter.htm", "refrigerator"),
    ("https://www.partselect.com/PS11740365-Whirlpool-W10830277-Evaporator-Fan-Motor.htm", "refrigerator"),
    ("https://www.partselect.com/PS11748020-Whirlpool-WPW10271509-Compressor-Start-Relay.htm", "refrigerator"),
    ("https://www.partselect.com/PS11753379-Whirlpool-WPW10348269-Pump-and-Motor-Assembly.htm", "dishwasher"),
    ("https://www.partselect.com/PS3406971-Whirlpool-W10300024-Drain-Pump.htm", "dishwasher"),
    ("https://www.partselect.com/PS11746119-Whirlpool-WPW10462039-Upper-Spray-Arm.htm", "dishwasher"),
]

# Map keywords in product names to subcategories
_SUBCATEGORY_MAP = {
    "ice maker": "ice_maker", "filter": "water_system",
    "shelf": "storage", "bin": "storage",
    "pump": "pump", "spray arm": "spray",
    "rack": "rack", "roller": "rack",
    "gasket": "seals", "seal": "seals",
    "fan": "cooling", "thermostat": "cooling",
    "compressor": "cooling", "defrost": "cooling",
    "dispenser": "dispenser", "detergent": "dispenser",
    "latch": "door", "hinge": "door",
    "heating": "heating", "element": "heating",
}


class PartSelectScraper:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self._playwright = None
        self._browser = None
        self._page = None

    def _start_browser(self):
        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self._page = ctx.new_page()
        Stealth().apply_stealth_sync(self._page)
        print("Stealth browser launched")

    def _stop_browser(self):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        print("Browser closed")

    def _navigate(self, url: str, retries: int = 2) -> BeautifulSoup | None:
        for attempt in range(retries):
            try:
                time.sleep(random.uniform(2.0, 4.0))
                self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(random.uniform(2.0, 4.0))

                title = self._page.title()
                if "Access Denied" in title or "Attention Required" in title:
                    print(f"  Blocked (attempt {attempt + 1}), backing off...")
                    time.sleep(10 * (attempt + 1))
                    self._page.reload(wait_until="domcontentloaded")
                    time.sleep(5)
                    if "Access Denied" in self._page.title():
                        continue

                return BeautifulSoup(self._page.content(), "lxml")
            except Exception as e:
                print(f"  Navigation error: {e}")
                time.sleep(5)
        return None

    def _parse_product_page(self, soup: BeautifulSoup, url: str, category: str) -> dict | None:
        try:
            ps_match = re.search(r"PS(\d+)", url)
            if not ps_match:
                return None
            ps_number = f"PS{ps_match.group(1)}"

            title_el = soup.select_one("h1")
            name = title_el.get_text(strip=True) if title_el else ""
            if not name:
                return None

            product = {
                "url": url,
                "category": category,
                "ps_number": ps_number,
                "name": name,
            }

            # Manufacturer part number
            for el in soup.select(".pd__mfr-part-number, .mfr-part-num"):
                text = el.get_text(strip=True)
                mpn = re.sub(r"^(Manufacturer|Mfr\.?)\s*(Part\s*#?\s*:?\s*)", "", text).strip()
                if mpn:
                    product["manufacturer_part"] = mpn
                    break
            else:
                product["manufacturer_part"] = ""

            # Price - try several selectors
            product["price"] = 0.0
            for sel in [".pd__price", "[itemprop=price]", ".js-partPrice", ".price"]:
                el = soup.select_one(sel)
                if el:
                    text = el.get("content", el.get_text(strip=True))
                    m = re.search(r"[\d]+\.[\d]{2}", str(text).replace(",", ""))
                    if m:
                        product["price"] = float(m.group())
                        break

            # Description
            desc_el = soup.select_one(".pd__description, [itemprop=description]")
            product["description"] = desc_el.get_text(strip=True)[:500] if desc_el else ""

            # Brand
            brand_el = soup.select_one("[itemprop=brand], .pd__brand")
            product["brand"] = brand_el.get_text(strip=True) if brand_el else ""

            # Rating
            rating_el = soup.select_one("[itemprop=ratingValue]")
            try:
                product["rating"] = float(rating_el.get("content", rating_el.get_text(strip=True))) if rating_el else 0.0
            except (ValueError, TypeError):
                product["rating"] = 0.0

            # Review count
            review_el = soup.select_one("[itemprop=reviewCount]")
            try:
                product["review_count"] = int(re.sub(r"[^\d]", "", review_el.get("content", review_el.get_text(strip=True)))) if review_el else 0
            except (ValueError, TypeError):
                product["review_count"] = 0

            # Stock
            stock_el = soup.select_one("[itemprop=availability]")
            if stock_el:
                stock_text = (stock_el.get("content", "") + stock_el.get_text()).lower()
                product["in_stock"] = "instock" in stock_text or "in stock" in stock_text
            else:
                product["in_stock"] = True

            # Image
            img_el = soup.select_one(".pd__image img, [itemprop=image]")
            product["image_url"] = img_el.get("src", img_el.get("data-src", "")) if img_el else ""

            # Compatible models
            models = []
            for a in soup.select('a[href*="/Models/"]'):
                m = re.search(r"/Models/([^/]+)", a.get("href", ""))
                if m and m.group(1) not in models:
                    models.append(m.group(1))
            product["compatible_models"] = models[:50]

            # Symptoms
            symptoms = []
            for el in soup.select(".pd__symptom, .symptom-link, .js-symptomName"):
                t = el.get_text(strip=True)
                if t and len(t) > 3:
                    symptoms.append(t)
            product["symptoms"] = symptoms

            # Installation difficulty
            page_text = soup.get_text().lower()
            if any(w in page_text for w in ["no tools", "snap", "tool-free"]):
                product["installation_difficulty"] = "easy"
            elif any(w in page_text for w in ["professional", "technician"]):
                product["installation_difficulty"] = "hard"
            else:
                product["installation_difficulty"] = "moderate"

            # Subcategory (keyword lookup)
            name_lower = name.lower()
            product["subcategory"] = "other"
            for keyword, subcat in _SUBCATEGORY_MAP.items():
                if keyword in name_lower:
                    product["subcategory"] = subcat
                    break

            return product

        except Exception as e:
            print(f"  Parse error: {e}")
            return None

    def _parse_model_page(self, soup: BeautifulSoup, model_number: str) -> dict | None:
        try:
            model = {
                "model_number": model_number,
                "url": f"{BASE_URL}/Models/{model_number}/",
            }

            title_el = soup.select_one("h1")
            model["name"] = title_el.get_text(strip=True) if title_el else model_number

            # Guess brand from name
            name_lower = model["name"].lower()
            model["brand"] = ""
            for brand in ["whirlpool", "samsung", "lg", "ge", "frigidaire",
                          "kitchenaid", "maytag", "kenmore", "bosch"]:
                if brand in name_lower:
                    model["brand"] = brand.title()
                    break

            # Appliance type
            page_text = soup.get_text().lower()[:1000]
            if "dishwasher" in page_text:
                model["appliance_type"] = "dishwasher"
            elif "refrigerator" in page_text or "fridge" in page_text:
                model["appliance_type"] = "refrigerator"
            else:
                model["appliance_type"] = "unknown"

            # Find compatible part links
            compatible_parts = []
            part_links = []
            for a in soup.select('a[href*="/PS"]'):
                href = a.get("href", "")
                m = re.search(r"PS(\d+)", href)
                if m:
                    ps = f"PS{m.group(1)}"
                    if ps not in compatible_parts:
                        compatible_parts.append(ps)
                    full_url = href if href.startswith("http") else BASE_URL + href
                    if full_url.endswith(".htm") and full_url not in part_links:
                        part_links.append(full_url)

            model["compatible_parts"] = compatible_parts
            model["part_links"] = part_links[:30]
            return model

        except Exception as e:
            print(f"  Model parse error: {e}")
            return None

    def run(self, max_products: int = 150):
        print("=" * 50)
        print("PartSelect Scraper (Playwright Stealth)")
        print("=" * 50)

        self._start_browser()
        all_products = []
        all_models = []
        seen_ps = set()

        try:
            # Phase 1: direct product URLs
            print(f"\nPhase 1: Scraping {len(DIRECT_PRODUCT_URLS)} product URLs...")
            for url, category in tqdm(DIRECT_PRODUCT_URLS, desc="Products"):
                ps_match = re.search(r"PS(\d+)", url)
                if ps_match:
                    ps_num = f"PS{ps_match.group(1)}"
                    if ps_num in seen_ps:
                        continue
                    seen_ps.add(ps_num)

                soup = self._navigate(url)
                if soup:
                    product = self._parse_product_page(soup, url, category)
                    if product and product.get("name"):
                        all_products.append(product)
                        print(f"  {product['ps_number']}: {product['name'][:50]} - ${product['price']}")

            # Phase 2: model pages + linked products
            print(f"\nPhase 2: Scraping {len(TARGET_MODELS)} model pages...")
            for model_num in tqdm(TARGET_MODELS, desc="Models"):
                url = f"{BASE_URL}/Models/{model_num}/"
                soup = self._navigate(url)
                if not soup:
                    continue

                model_data = self._parse_model_page(soup, model_num)
                if model_data:
                    all_models.append(model_data)
                    print(f"  {model_num}: {len(model_data.get('compatible_parts', []))} parts")

                    for part_url in model_data.get("part_links", [])[:5]:
                        if len(all_products) >= max_products:
                            break
                        ps_m = re.search(r"PS(\d+)", part_url)
                        if ps_m:
                            ps_num = f"PS{ps_m.group(1)}"
                            if ps_num in seen_ps:
                                continue
                            seen_ps.add(ps_num)

                        cat = model_data.get("appliance_type", "refrigerator")
                        p_soup = self._navigate(part_url)
                        if p_soup:
                            product = self._parse_product_page(p_soup, part_url, cat)
                            if product and product.get("name"):
                                all_products.append(product)
                                print(f"    {product['ps_number']}: {product['name'][:50]}")

                if len(all_products) >= max_products:
                    print(f"\n  Hit max products limit ({max_products})")
                    break

            # Save
            products_file = os.path.join(DATA_DIR, "products.json")
            models_file = os.path.join(DATA_DIR, "models.json")
            with open(products_file, "w") as f:
                json.dump(all_products, f, indent=2)
            with open(models_file, "w") as f:
                json.dump(all_models, f, indent=2)

            print(f"\n{'=' * 50}")
            print(f"Done! {len(all_products)} products, {len(all_models)} models")
            print(f"  -> {products_file}")
            print(f"  -> {models_file}")

        finally:
            self._stop_browser()

        return all_products, all_models


def main():
    PartSelectScraper().run()


if __name__ == "__main__":
    main()
