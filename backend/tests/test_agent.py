"""End-to-end agent workflow tests against the seeded warehouse."""
from __future__ import annotations

from app.agent import QueryPilot
from app.providers import DeterministicProvider


def test_deterministic_provider_maps_known_questions():
    p = DeterministicProvider()
    assert "SUM(total)" in p.generate("what is our total revenue?").sql
    assert "GROUP BY status" in p.generate("orders by status").sql.replace("group by status", "GROUP BY status")
    assert p.generate("purple monkey dishwasher").confidence == 0.0


def test_aggregate_query_runs_automatically():
    pilot = QueryPilot()
    state = pilot.ask("total revenue")
    assert state.status == "completed"
    assert state.rows and state.rows[0][0] > 0
    step_names = [s.name for s in state.trace]
    assert step_names[:4] == ["retrieve_schema", "generate_sql", "validate", "guard"]


def test_revenue_by_category_returns_chart():
    pilot = QueryPilot()
    state = pilot.ask("revenue by category")
    assert state.status == "completed"
    assert state.chart is not None
    assert state.chart["type"] == "bar"


def test_row_level_query_needs_approval_then_runs():
    pilot = QueryPilot()
    state = pilot.ask("list customers")
    assert state.status == "needs_approval"
    assert any(s.name == "guard" and s.status == "pending" for s in state.trace)

    approved = pilot.approve(state.id)
    assert approved.status == "completed"
    assert approved.columns[:2] == ["id", "name"]


def test_row_level_query_can_be_rejected():
    pilot = QueryPilot()
    state = pilot.ask("show orders")
    assert state.status == "needs_approval"
    rejected = pilot.reject(state.id)
    assert rejected.status == "rejected"


def test_unmappable_question_is_rejected_gracefully():
    pilot = QueryPilot()
    state = pilot.ask("tell me a joke")
    assert state.status == "rejected"
    assert state.sql == ""


def test_history_records_queries():
    pilot = QueryPilot()
    pilot.ask("total revenue")
    pilot.ask("top 5 products")
    assert len(pilot.history()) >= 2
