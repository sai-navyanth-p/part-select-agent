"""Load seed and scraped data into SQLite + ChromaDB.

Run as: PYTHONPATH=. python -m data.load_data
"""

import os
import json
from data.database import (
    init_db, upsert_part, upsert_model, add_compatibility,
    get_connection, get_stats,
)
from data.vector_store import get_vector_store

SCRAPED_DIR = os.path.join(os.path.dirname(__file__), "scraped")


def load_scraped_data():
    """Load scraped JSON files into the database."""
    products_file = os.path.join(SCRAPED_DIR, "products.json")
    models_file = os.path.join(SCRAPED_DIR, "models.json")

    if not os.path.exists(products_file):
        print("No scraped data found. Run the scraper first or use seed data.")
        return False

    init_db()
    vs = get_vector_store()

    with open(products_file) as f:
        products = json.load(f)
    print(f"Loading {len(products)} scraped products...")
    for p in products:
        upsert_part(p)
        vs.add_product(p)

    if os.path.exists(models_file):
        with open(models_file) as f:
            models = json.load(f)
        print(f"Loading {len(models)} scraped models...")
        for m in models:
            upsert_model(m)
            for ps_num in m.get("compatible_parts", []):
                add_compatibility(ps_num, m["model_number"])

    # Also wire up compatible_models listed on each product
    for p in products:
        for model_num in p.get("compatible_models", []):
            add_compatibility(p["ps_number"], model_num)

    stats = get_stats()
    vs_stats = vs.get_stats()
    print(f"Scraped data loaded. SQLite: {stats} | ChromaDB: {vs_stats}")
    return True


def load_seed_data():
    """Load hardcoded seed data (products, models, guides, orders)."""
    from data.seed_data import SEED_PRODUCTS, SEED_MODELS, SEED_GUIDES, SEED_ORDERS

    init_db()
    vs = get_vector_store()
    conn = get_connection()
    cursor = conn.cursor()

    print(f"Loading {len(SEED_PRODUCTS)} seed products...")
    for p in SEED_PRODUCTS:
        upsert_part(p)
        vs.add_product(p)

    print(f"Loading {len(SEED_MODELS)} seed models...")
    for m in SEED_MODELS:
        upsert_model(m)
        for ps_num in m.get("compatible_parts", []):
            add_compatibility(ps_num, m["model_number"])

    # Troubleshooting guides
    print("Loading troubleshooting guides...")
    for category, problems in SEED_GUIDES.get("troubleshooting", {}).items():
        for key, guide in problems.items():
            cursor.execute("""
                INSERT OR REPLACE INTO troubleshooting_guides
                (category, problem_key, title, symptoms, diagnosis_steps)
                VALUES (?, ?, ?, ?, ?)
            """, (
                category, key, guide["title"],
                json.dumps(guide.get("symptoms", [])),
                json.dumps(guide.get("diagnosis_steps", [])),
            ))
            guide_id = cursor.lastrowid
            for ps_num in guide.get("recommended_parts", []):
                part_row = cursor.execute(
                    "SELECT id FROM parts WHERE ps_number=?", (ps_num,)
                ).fetchone()
                if part_row:
                    cursor.execute(
                        "INSERT OR IGNORE INTO guide_parts (guide_id, part_id) VALUES (?, ?)",
                        (guide_id, part_row[0]),
                    )
            vs.add_guide({"problem_key": key, "category": category, **guide})

    # Installation guides
    print("Loading installation guides...")
    for ps_num, ig in SEED_GUIDES.get("installation", {}).items():
        part_row = cursor.execute(
            "SELECT id FROM parts WHERE ps_number=?", (ps_num,)
        ).fetchone()
        if part_row:
            cursor.execute("""
                INSERT OR REPLACE INTO installation_guides
                (part_id, difficulty, time_estimate, tools_needed, safety_warnings, steps)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                part_row[0],
                ig.get("difficulty", "moderate"),
                ig.get("time_estimate", ""),
                json.dumps(ig.get("tools_needed", [])),
                json.dumps(ig.get("safety_warnings", [])),
                json.dumps(ig.get("steps", [])),
            ))

    # Sample orders
    print("Loading sample orders...")
    for oid, order in SEED_ORDERS.items():
        cursor.execute("""
            INSERT OR REPLACE INTO orders
            (order_id, status, customer_name, order_date, estimated_delivery,
             total, tracking_number, carrier, items)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            oid, order.get("status", ""),
            order.get("customer_name", ""),
            order.get("order_date", ""),
            order.get("estimated_delivery", ""),
            order.get("total", 0.0),
            order.get("tracking_number", ""),
            order.get("carrier", ""),
            json.dumps(order.get("items", [])),
        ))

    conn.commit()
    conn.close()

    stats = get_stats()
    vs_stats = vs.get_stats()
    print(f"Seed data loaded. SQLite: {stats} | ChromaDB: {vs_stats}")
    return True


def main():
    """Seed first, then merge scraped data on top."""
    print("=" * 50)
    print("PartSelect Data Loader")
    print("=" * 50)

    print("\nStep 1: Loading seed data...")
    load_seed_data()

    products_file = os.path.join(SCRAPED_DIR, "products.json")
    if os.path.exists(products_file):
        print("\nStep 2: Merging scraped data...")
        load_scraped_data()
    else:
        print("\nNo scraped data found. Using seed data only.")
        print("Run 'PYTHONPATH=. python -m scraper.scraper' to scrape real data.\n")


if __name__ == "__main__":
    main()
