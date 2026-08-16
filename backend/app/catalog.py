"""Semantic catalog: human descriptions + synonyms for schema-aware grounding.

Used both to render the schema in the UI and to help the NL->SQL layer map
business language ("revenue", "buyers") to concrete tables/columns.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ColumnMeta:
    name: str
    type: str
    description: str
    synonyms: list[str] = field(default_factory=list)


@dataclass
class TableMeta:
    name: str
    description: str
    columns: list[ColumnMeta]
    synonyms: list[str] = field(default_factory=list)


CATALOG: dict[str, TableMeta] = {
    "customers": TableMeta(
        name="customers",
        description="Registered shoppers.",
        synonyms=["buyers", "users", "clients", "shoppers"],
        columns=[
            ColumnMeta("id", "INTEGER", "Primary key"),
            ColumnMeta("name", "TEXT", "Full name"),
            ColumnMeta("country", "TEXT", "ISO-ish country code", ["region", "location"]),
            ColumnMeta("created_at", "TEXT", "Signup timestamp", ["signup", "joined"]),
        ],
    ),
    "products": TableMeta(
        name="products",
        description="Catalog of products for sale.",
        synonyms=["items", "sku", "catalog"],
        columns=[
            ColumnMeta("id", "INTEGER", "Primary key"),
            ColumnMeta("name", "TEXT", "Product name"),
            ColumnMeta("category", "TEXT", "Product category", ["type", "department"]),
            ColumnMeta("price", "REAL", "List price", ["cost"]),
        ],
    ),
    "orders": TableMeta(
        name="orders",
        description="Placed orders with a status and total.",
        synonyms=["purchases", "sales", "transactions"],
        columns=[
            ColumnMeta("id", "INTEGER", "Primary key"),
            ColumnMeta("customer_id", "INTEGER", "FK -> customers.id"),
            ColumnMeta("status", "TEXT", "Order status", ["state"]),
            ColumnMeta("total", "REAL", "Order total amount", ["revenue", "amount", "sales", "value"]),
            ColumnMeta("created_at", "TEXT", "Order timestamp", ["date", "when", "time"]),
        ],
    ),
    "order_items": TableMeta(
        name="order_items",
        description="Line items belonging to an order.",
        synonyms=["line items", "cart items"],
        columns=[
            ColumnMeta("id", "INTEGER", "Primary key"),
            ColumnMeta("order_id", "INTEGER", "FK -> orders.id"),
            ColumnMeta("product_id", "INTEGER", "FK -> products.id"),
            ColumnMeta("quantity", "INTEGER", "Units purchased", ["qty", "units"]),
            ColumnMeta("unit_price", "REAL", "Price per unit"),
        ],
    ),
}

ALLOWED_TABLES = set(CATALOG.keys())


def schema_as_dict() -> list[dict]:
    return [
        {
            "table": t.name,
            "description": t.description,
            "synonyms": t.synonyms,
            "columns": [
                {"name": c.name, "type": c.type, "description": c.description, "synonyms": c.synonyms}
                for c in t.columns
            ],
        }
        for t in CATALOG.values()
    ]


def schema_prompt() -> str:
    """Compact DDL-ish schema string suitable for grounding an LLM prompt."""
    lines = []
    for t in CATALOG.values():
        cols = ", ".join(f"{c.name} {c.type}" for c in t.columns)
        lines.append(f"-- {t.description}\n{t.name}({cols})")
    return "\n".join(lines)
