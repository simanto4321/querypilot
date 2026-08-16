"""NL -> SQL providers.

- ``DeterministicProvider`` (default): an offline, dependency-free intent matcher
  that maps common analytics questions to grounded SQL. It makes the whole system
  runnable and testable with no API key.
- ``OpenAIProvider`` (optional): grounds a hosted LLM with the semantic schema.

Both return a :class:`Generation` with SQL, a confidence score and a short
rationale. The SQL is *never trusted* - it always passes through the validator
and guard before execution.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .catalog import schema_prompt
from .config import get_settings


@dataclass
class Generation:
    sql: str
    confidence: float
    rationale: str
    provider: str


def _top_n(text: str, default: int = 10) -> int:
    m = re.search(r"top\s+(\d{1,3})", text)
    if m:
        return max(1, min(int(m.group(1)), 100))
    return default


class DeterministicProvider:
    name = "deterministic"

    def generate(self, question: str) -> Generation:
        q = question.lower().strip()
        n = _top_n(q)

        rules: list[tuple[list[str], str, str]] = [
            (
                ["list customers", "show customers", "all customers", "customer list"],
                f"SELECT id, name, country, created_at FROM customers ORDER BY created_at DESC LIMIT {n}",
                "Row-level customer records (governed: requires approval).",
            ),
            (
                ["list orders", "show orders", "recent orders", "latest orders"],
                f"SELECT id, customer_id, status, total, created_at FROM orders ORDER BY created_at DESC LIMIT {n}",
                "Row-level order records (governed: requires approval).",
            ),
            (
                ["revenue by month", "monthly revenue", "sales by month", "revenue per month"],
                "SELECT substr(created_at,1,7) AS month, ROUND(SUM(total),2) AS revenue "
                "FROM orders WHERE status <> 'cancelled' GROUP BY month ORDER BY month",
                "Monthly revenue from non-cancelled orders.",
            ),
            (
                ["revenue by category", "sales by category", "category revenue"],
                "SELECT p.category AS category, ROUND(SUM(oi.quantity * oi.unit_price),2) AS revenue "
                "FROM order_items oi JOIN products p ON p.id = oi.product_id "
                "GROUP BY p.category ORDER BY revenue DESC",
                "Revenue per product category from order line items.",
            ),
            (
                ["top products", "best selling", "best-selling", "top selling", "top-selling", "popular products"],
                f"SELECT p.name AS product, ROUND(SUM(oi.quantity * oi.unit_price),2) AS revenue "
                f"FROM order_items oi JOIN products p ON p.id = oi.product_id "
                f"GROUP BY p.name ORDER BY revenue DESC LIMIT {n}",
                f"Top {n} products by revenue.",
            ),
            (
                ["top customers", "biggest customers", "best customers", "highest spending"],
                f"SELECT c.name AS customer, ROUND(SUM(o.total),2) AS spend "
                f"FROM orders o JOIN customers c ON c.id = o.customer_id "
                f"WHERE o.status <> 'cancelled' GROUP BY c.name ORDER BY spend DESC LIMIT {n}",
                f"Top {n} customers by total spend.",
            ),
            (
                ["orders by status", "status breakdown", "orders per status"],
                "SELECT status, COUNT(*) AS orders FROM orders GROUP BY status ORDER BY orders DESC",
                "Order counts grouped by status.",
            ),
            (
                ["average order value", "avg order", "aov", "average order"],
                "SELECT ROUND(AVG(total),2) AS average_order_value FROM orders WHERE status <> 'cancelled'",
                "Average order value across non-cancelled orders.",
            ),
            (
                ["customers by country", "where are my customers", "customers per country", "customers by region"],
                "SELECT country, COUNT(*) AS customers FROM customers GROUP BY country ORDER BY customers DESC",
                "Customer counts by country.",
            ),
            (
                ["new customers by month", "signups by month", "new customers per month"],
                "SELECT substr(created_at,1,7) AS month, COUNT(*) AS new_customers "
                "FROM customers GROUP BY month ORDER BY month",
                "New customer signups per month.",
            ),
            (
                ["how many orders", "number of orders", "count of orders", "total orders", "order count"],
                "SELECT COUNT(*) AS orders FROM orders",
                "Total number of orders.",
            ),
            (
                ["how many customers", "number of customers", "total customers", "customer count"],
                "SELECT COUNT(*) AS customers FROM customers",
                "Total number of customers.",
            ),
            (
                ["how many products", "number of products", "total products", "product count"],
                "SELECT COUNT(*) AS products FROM products",
                "Total number of products.",
            ),
            (
                ["total revenue", "total sales", "how much revenue", "overall revenue", "revenue"],
                "SELECT ROUND(SUM(total),2) AS total_revenue FROM orders WHERE status <> 'cancelled'",
                "Total revenue from non-cancelled orders.",
            ),
        ]

        for keywords, sql, rationale in rules:
            if any(k in q for k in keywords):
                return Generation(sql=sql, confidence=0.9, rationale=rationale, provider=self.name)

        return Generation(
            sql="",
            confidence=0.0,
            rationale=(
                "I couldn't confidently map that question to the schema. Try e.g. "
                "'total revenue', 'revenue by month', 'top 5 products', 'orders by status'."
            ),
            provider=self.name,
        )


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def generate(self, question: str) -> Generation:
        import httpx  # local import so the app runs without httpx configured

        system = (
            "You translate questions into a single read-only SQLite SELECT over this schema. "
            "Return ONLY SQL, no prose.\n\n" + schema_prompt()
        )
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": question},
                ],
            },
            timeout=30,
        )
        resp.raise_for_status()
        sql = resp.json()["choices"][0]["message"]["content"].strip()
        sql = re.sub(r"^```(sql)?|```$", "", sql, flags=re.IGNORECASE | re.MULTILINE).strip()
        return Generation(sql=sql, confidence=0.75, rationale="Generated by hosted LLM.", provider=self.name)


def get_provider():
    settings = get_settings()
    if settings.llm_provider == "openai" and settings.openai_api_key:
        return OpenAIProvider(settings.openai_api_key, settings.openai_model)
    return DeterministicProvider()
