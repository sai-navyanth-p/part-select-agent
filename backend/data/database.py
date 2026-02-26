"""SQLite database for parts, models, guides, and orders."""

import os
import json
import sqlite3
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "partselect.db")


@contextmanager
def _connect():
    """Yield a connection with row_factory, WAL, and FK enforcement."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_connection() -> sqlite3.Connection:
    """Get a raw connection (used by load_data where caller manages lifecycle)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


SCHEMA = """\
CREATE TABLE IF NOT EXISTS parts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ps_number TEXT UNIQUE NOT NULL,
    manufacturer_part TEXT DEFAULT '',
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    price REAL DEFAULT 0.0,
    category TEXT DEFAULT '',
    subcategory TEXT DEFAULT '',
    brand TEXT DEFAULT '',
    image_url TEXT DEFAULT '',
    url TEXT DEFAULT '',
    in_stock BOOLEAN DEFAULT 1,
    rating REAL DEFAULT 0.0,
    review_count INTEGER DEFAULT 0,
    installation_difficulty TEXT DEFAULT 'moderate',
    symptoms TEXT DEFAULT '[]',
    installation_steps TEXT DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_number TEXT UNIQUE NOT NULL,
    brand TEXT DEFAULT '',
    appliance_type TEXT DEFAULT '',
    name TEXT DEFAULT '',
    url TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS part_model_compatibility (
    part_id INTEGER NOT NULL,
    model_id INTEGER NOT NULL,
    PRIMARY KEY (part_id, model_id),
    FOREIGN KEY (part_id) REFERENCES parts(id) ON DELETE CASCADE,
    FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS troubleshooting_guides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    problem_key TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    symptoms TEXT DEFAULT '[]',
    diagnosis_steps TEXT DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS guide_parts (
    guide_id INTEGER NOT NULL,
    part_id INTEGER NOT NULL,
    PRIMARY KEY (guide_id, part_id),
    FOREIGN KEY (guide_id) REFERENCES troubleshooting_guides(id) ON DELETE CASCADE,
    FOREIGN KEY (part_id) REFERENCES parts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS installation_guides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_id INTEGER NOT NULL,
    difficulty TEXT DEFAULT 'moderate',
    time_estimate TEXT DEFAULT '',
    tools_needed TEXT DEFAULT '[]',
    safety_warnings TEXT DEFAULT '[]',
    steps TEXT DEFAULT '[]',
    FOREIGN KEY (part_id) REFERENCES parts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'processing',
    customer_name TEXT DEFAULT '',
    order_date TEXT DEFAULT '',
    estimated_delivery TEXT DEFAULT '',
    total REAL DEFAULT 0.0,
    tracking_number TEXT DEFAULT '',
    carrier TEXT DEFAULT '',
    items TEXT DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_parts_ps ON parts(ps_number);
CREATE INDEX IF NOT EXISTS idx_parts_category ON parts(category);
CREATE INDEX IF NOT EXISTS idx_parts_brand ON parts(brand);
CREATE INDEX IF NOT EXISTS idx_models_number ON models(model_number);
CREATE INDEX IF NOT EXISTS idx_models_type ON models(appliance_type);
CREATE INDEX IF NOT EXISTS idx_orders_id ON orders(order_id);
"""


def init_db():
    with _connect() as conn:
        conn.executescript(SCHEMA)
    print(f"Database initialized: {DB_PATH}")


# -- Mutations --

def upsert_part(part: dict) -> int:
    with _connect() as conn:
        cur = conn.execute("""
            INSERT INTO parts (ps_number, manufacturer_part, name, description, price,
                category, subcategory, brand, image_url, url, in_stock, rating,
                review_count, installation_difficulty, symptoms, installation_steps)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ps_number) DO UPDATE SET
                manufacturer_part=excluded.manufacturer_part,
                name=excluded.name, description=excluded.description,
                price=excluded.price, category=excluded.category,
                subcategory=excluded.subcategory, brand=excluded.brand,
                image_url=excluded.image_url, url=excluded.url,
                in_stock=excluded.in_stock, rating=excluded.rating,
                review_count=excluded.review_count,
                installation_difficulty=excluded.installation_difficulty,
                symptoms=excluded.symptoms, installation_steps=excluded.installation_steps
        """, (
            part.get("ps_number", ""),
            part.get("manufacturer_part", ""),
            part.get("name", ""),
            part.get("description", ""),
            part.get("price", 0.0),
            part.get("category", ""),
            part.get("subcategory", ""),
            part.get("brand", ""),
            part.get("image_url", ""),
            part.get("url", ""),
            part.get("in_stock", True),
            part.get("rating", 0.0),
            part.get("review_count", 0),
            part.get("installation_difficulty", "moderate"),
            json.dumps(part.get("symptoms", [])),
            json.dumps(part.get("installation_steps", [])),
        ))
        return cur.lastrowid or conn.execute(
            "SELECT id FROM parts WHERE ps_number=?", (part["ps_number"],)
        ).fetchone()[0]


def upsert_model(model: dict) -> int:
    with _connect() as conn:
        cur = conn.execute("""
            INSERT INTO models (model_number, brand, appliance_type, name, url)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(model_number) DO UPDATE SET
                brand=excluded.brand, appliance_type=excluded.appliance_type,
                name=excluded.name, url=excluded.url
        """, (
            model.get("model_number", ""),
            model.get("brand", ""),
            model.get("appliance_type", ""),
            model.get("name", ""),
            model.get("url", ""),
        ))
        return cur.lastrowid or conn.execute(
            "SELECT id FROM models WHERE model_number=?", (model["model_number"],)
        ).fetchone()[0]


def add_compatibility(ps_number: str, model_number: str):
    with _connect() as conn:
        part = conn.execute("SELECT id FROM parts WHERE ps_number=?", (ps_number,)).fetchone()
        model = conn.execute("SELECT id FROM models WHERE model_number=?", (model_number,)).fetchone()
        if part and model:
            conn.execute(
                "INSERT OR IGNORE INTO part_model_compatibility (part_id, model_id) VALUES (?, ?)",
                (part[0], model[0]),
            )


# -- Queries --

def search_parts(query: str, category: str = None, limit: int = 10) -> list[dict]:
    with _connect() as conn:
        like = f"%{query}%"
        params = [like] * 5
        sql = """
            SELECT * FROM parts
            WHERE (name LIKE ? OR ps_number LIKE ? OR manufacturer_part LIKE ?
                   OR description LIKE ? OR brand LIKE ?)
        """
        if category:
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY rating DESC, review_count DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_part_by_ps(ps_number: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM parts WHERE ps_number = ?", (ps_number,)).fetchone()
        return dict(row) if row else None


def check_compatibility(ps_number: str, model_number: str) -> dict:
    with _connect() as conn:
        part = conn.execute("SELECT * FROM parts WHERE ps_number = ?", (ps_number,)).fetchone()
        if not part:
            return {"found": False, "error": f"Part {ps_number} not found"}

        part_dict = dict(part)
        model = conn.execute("SELECT * FROM models WHERE model_number = ?", (model_number,)).fetchone()

        if not model:
            return {
                "found": True, "compatible": None,
                "part": part_dict, "model_number": model_number,
                "message": f"Model {model_number} not in our database. Verify on PartSelect.com.",
            }

        count = conn.execute(
            "SELECT COUNT(*) FROM part_model_compatibility WHERE part_id=? AND model_id=?",
            (part["id"], model["id"]),
        ).fetchone()[0]

        compatible = count > 0
        return {
            "found": True, "compatible": compatible,
            "part": part_dict, "model_number": model_number,
            "model_info": dict(model),
            "message": (
                f"{part_dict['name']} ({ps_number}) IS compatible with {model_number}."
                if compatible
                else f"{part_dict['name']} ({ps_number}) is NOT confirmed compatible with {model_number}."
            ),
        }


def get_model_info(model_number: str) -> dict | None:
    with _connect() as conn:
        model = conn.execute("SELECT * FROM models WHERE model_number = ?", (model_number,)).fetchone()
        if not model:
            return None
        out = dict(model)
        parts = conn.execute("""
            SELECT p.* FROM parts p
            JOIN part_model_compatibility pmc ON p.id = pmc.part_id
            WHERE pmc.model_id = ?
            ORDER BY p.category, p.name
        """, (model["id"],)).fetchall()
        out["compatible_parts"] = [dict(p) for p in parts]
        return out


def get_compatible_models(ps_number: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("""
            SELECT m.* FROM models m
            JOIN part_model_compatibility pmc ON m.id = pmc.model_id
            JOIN parts p ON p.id = pmc.part_id
            WHERE p.ps_number = ?
        """, (ps_number,)).fetchall()
        return [dict(r) for r in rows]


def find_troubleshooting_guide(category: str, symptom: str) -> dict | None:
    with _connect() as conn:
        guides = conn.execute(
            "SELECT * FROM troubleshooting_guides WHERE category = ?", (category,)
        ).fetchall()

        symptom_lower = symptom.lower()
        best, best_score = None, 0

        for g in guides:
            gd = dict(g)
            score = 0
            for s in json.loads(gd["symptoms"]):
                if any(w in symptom_lower for w in s.lower().split()):
                    score += 1
            if any(w in symptom_lower for w in gd["title"].lower().split()):
                score += 2
            if score > best_score:
                best_score, best = score, gd

        if best:
            parts = conn.execute("""
                SELECT p.* FROM parts p
                JOIN guide_parts gp ON p.id = gp.part_id
                WHERE gp.guide_id = ?
            """, (best["id"],)).fetchall()
            best["recommended_parts"] = [dict(p) for p in parts]
            best["symptoms"] = json.loads(best["symptoms"])
            best["diagnosis_steps"] = json.loads(best["diagnosis_steps"])

        return best


def get_installation_guide(ps_number: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("""
            SELECT ig.*, p.name as part_name, p.ps_number
            FROM installation_guides ig
            JOIN parts p ON p.id = ig.part_id
            WHERE p.ps_number = ?
        """, (ps_number,)).fetchone()
        if not row:
            return None
        g = dict(row)
        for key in ("tools_needed", "safety_warnings", "steps"):
            g[key] = json.loads(g[key])
        return g


def lookup_order(order_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["items"] = json.loads(d["items"])
        return d


def get_stats() -> dict:
    with _connect() as conn:
        return {
            "parts": conn.execute("SELECT COUNT(*) FROM parts").fetchone()[0],
            "models": conn.execute("SELECT COUNT(*) FROM models").fetchone()[0],
            "compatibility_links": conn.execute("SELECT COUNT(*) FROM part_model_compatibility").fetchone()[0],
            "troubleshooting_guides": conn.execute("SELECT COUNT(*) FROM troubleshooting_guides").fetchone()[0],
            "installation_guides": conn.execute("SELECT COUNT(*) FROM installation_guides").fetchone()[0],
            "orders": conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        }
