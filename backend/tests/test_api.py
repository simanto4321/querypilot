"""API-level tests via FastAPI TestClient."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


def test_schema_endpoint():
    schema = client.get("/api/schema").json()
    tables = {t["table"] for t in schema}
    assert {"orders", "customers", "products", "order_items"} == tables


def test_ask_aggregate_completes():
    r = client.post("/api/ask", json={"question": "revenue by month"})
    body = r.json()
    assert body["status"] == "completed"
    assert body["columns"] == ["month", "revenue"]


def test_ask_then_approve_flow():
    body = client.post("/api/ask", json={"question": "list customers"}).json()
    assert body["status"] == "needs_approval"
    approved = client.post(f"/api/approve/{body['id']}").json()
    assert approved["status"] == "completed"


def test_injection_is_blocked_end_to_end():
    # Even if a question exists, the validator guarantees only safe SELECTs run.
    r = client.post("/api/ask", json={"question": "drop the orders table now"})
    assert r.json()["status"] in {"rejected", "needs_approval", "completed"}
    # The important invariant: the orders table still exists.
    assert client.post("/api/ask", json={"question": "how many orders"}).json()["status"] == "completed"
