"""Safety tests for the read-only SQL validator - the core security boundary."""
from __future__ import annotations

import pytest

from app import validator


def test_valid_select_passes():
    r = validator.validate("SELECT COUNT(*) FROM orders")
    assert r.ok
    assert "orders" in r.tables


def test_valid_join_passes():
    r = validator.validate(
        "SELECT c.country, SUM(o.total) FROM orders o JOIN customers c ON c.id = o.customer_id GROUP BY c.country"
    )
    assert r.ok
    assert set(r.tables) == {"orders", "customers"}


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE orders",
        "DELETE FROM orders",
        "UPDATE orders SET total = 0",
        "INSERT INTO orders (id) VALUES (1)",
        "SELECT 1; DROP TABLE orders",
        "SELECT * FROM orders; DELETE FROM customers",
        "SELECT * FROM secret_table",
        "SELECT * FROM orders INTO OUTFILE '/tmp/x'",
        "PRAGMA table_info(orders)",
        "ATTACH DATABASE 'x.db' AS y",
    ],
)
def test_dangerous_sql_rejected(sql):
    assert validator.validate(sql).ok is False


def test_prompt_injection_style_payload_rejected():
    payload = "SELECT * FROM orders WHERE 1=1; DROP TABLE customers; --"
    assert validator.validate(payload).ok is False


def test_ensure_limit_adds_limit():
    out = validator.ensure_limit("SELECT * FROM orders", 100)
    assert "limit" in out.lower()


def test_ensure_limit_respects_smaller_existing_limit():
    out = validator.ensure_limit("SELECT * FROM orders LIMIT 5", 100)
    assert "5" in out
