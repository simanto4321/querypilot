"""Read-only accessor + seed for the sample analytics warehouse."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from .config import get_settings

RNG = random.Random(7)


@lru_cache
def engine() -> Engine:
    url = get_settings().warehouse_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)


def list_tables() -> list[str]:
    return sorted(inspect(engine()).get_table_names())


def run_select(sql: str, params: dict | None = None, limit: int | None = None) -> tuple[list[str], list[list]]:
    """Execute a read-only SELECT and return (columns, rows)."""
    with engine().connect() as conn:
        result = conn.execute(text(sql), params or {})
        columns = list(result.keys())
        raw = result.fetchmany(limit) if limit else result.fetchall()
        return columns, [list(r) for r in raw]


def explain(sql: str) -> str:
    dialect_prefix = "EXPLAIN QUERY PLAN " if get_settings().warehouse_url.startswith("sqlite") else "EXPLAIN "
    with engine().connect() as conn:
        rows = conn.execute(text(dialect_prefix + sql)).fetchall()
        return "\n".join(str(tuple(r)) for r in rows)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def seed() -> None:
    """Create and populate a small e-commerce analytics warehouse."""
    ddl = [
        "DROP TABLE IF EXISTS order_items",
        "DROP TABLE IF EXISTS orders",
        "DROP TABLE IF EXISTS products",
        "DROP TABLE IF EXISTS customers",
        "CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, country TEXT, created_at TEXT)",
        "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, category TEXT, price REAL)",
        "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, status TEXT, total REAL, created_at TEXT)",
        "CREATE TABLE order_items (id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER, quantity INTEGER, unit_price REAL)",
    ]
    now = datetime.now(timezone.utc)
    countries = ["US", "GB", "BD", "DE", "IN", "CA"]
    categories = ["electronics", "apparel", "home", "beauty"]
    statuses = ["pending", "paid", "shipped", "delivered", "cancelled"]
    first = ["Ada", "Grace", "Alan", "Linus", "Katherine", "Dennis", "Barbara", "Ken", "Radia", "Margaret"]
    last = ["Lovelace", "Hopper", "Turing", "Torvalds", "Johnson", "Ritchie", "Liskov", "Thompson", "Perlman", "Hamilton"]

    customers, products, orders, items = [], [], [], []
    for cid in range(1, 301):
        customers.append({
            "id": cid,
            "name": f"{RNG.choice(first)} {RNG.choice(last)}",
            "country": RNG.choice(countries),
            "created_at": _iso(now - timedelta(days=RNG.randint(1, 500))),
        })
    prod_names = ["Nova", "Aurora", "Zephyr", "Quartz", "Pixel", "Comet", "Lumen", "Vertex", "Onyx", "Halo"]
    for pid in range(1, 61):
        products.append({
            "id": pid,
            "name": f"{RNG.choice(prod_names)} {pid}",
            "category": RNG.choice(categories),
            "price": round(RNG.uniform(9, 900), 2),
        })
    item_id = 1
    for oid in range(1, 1201):
        created = now - timedelta(days=RNG.randint(0, 365))
        total = 0.0
        line_items = []
        for _ in range(RNG.randint(1, 4)):
            pid = RNG.randint(1, 60)
            qty = RNG.randint(1, 5)
            price = products[pid - 1]["price"]
            total += qty * price
            line_items.append({"id": item_id, "order_id": oid, "product_id": pid, "quantity": qty, "unit_price": price})
            item_id += 1
        items.extend(line_items)
        orders.append({
            "id": oid,
            "customer_id": RNG.randint(1, 300),
            "status": RNG.choice(statuses),
            "total": round(total, 2),
            "created_at": _iso(created),
        })

    with engine().begin() as conn:
        for stmt in ddl:
            conn.execute(text(stmt))
        conn.execute(text("INSERT INTO customers (id,name,country,created_at) VALUES (:id,:name,:country,:created_at)"), customers)
        conn.execute(text("INSERT INTO products (id,name,category,price) VALUES (:id,:name,:category,:price)"), products)
        conn.execute(text("INSERT INTO orders (id,customer_id,status,total,created_at) VALUES (:id,:customer_id,:status,:total,:created_at)"), orders)
        conn.execute(text("INSERT INTO order_items (id,order_id,product_id,quantity,unit_price) VALUES (:id,:order_id,:product_id,:quantity,:unit_price)"), items)


if __name__ == "__main__":
    seed()
    print("Seeded QueryPilot warehouse: 300 customers, 60 products, 1200 orders.")
