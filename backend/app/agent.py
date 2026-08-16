"""The QueryPilot agent workflow.

A small, explicit graph of nodes with a recorded trace:

    retrieve_schema -> generate_sql -> validate -> guard -> [approval?] -> execute -> format

The guard implements a governance policy: aggregate/analytics queries run
automatically, while row-level data dumps (or queries estimated to scan more
than a threshold) are held for human approval. Every generated SQL statement is
validated as a single read-only SELECT before it can run.
"""
from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import validator, warehouse
from .catalog import schema_as_dict
from .config import get_settings
from .providers import Generation, get_provider

_AGG_RE = re.compile(r"\b(sum|count|avg|min|max|group\s+by)\b", re.IGNORECASE)


@dataclass
class TraceStep:
    name: str
    status: str  # ok | fail | skip | pending
    duration_ms: float
    detail: str = ""


@dataclass
class QueryState:
    id: str
    question: str
    provider: str = ""
    rationale: str = ""
    confidence: float = 0.0
    sql: str = ""
    safe_sql: str = ""
    status: str = "pending"  # completed | needs_approval | rejected | error
    tables: list[str] = field(default_factory=list)
    estimated_rows: int = 0
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    chart: dict | None = None
    trace: list[TraceStep] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["trace"] = [t.__dict__ for t in self.trace]
        return d


class Timer:
    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.ms = round((time.perf_counter() - self._start) * 1000, 2)


def _estimate_rows(tables: list[str]) -> int:
    best = 0
    for t in tables:
        try:
            n = warehouse.run_select(f"SELECT COUNT(*) AS n FROM {t}")[1][0][0]
            best = max(best, int(n))
        except Exception:  # noqa: BLE001
            continue
    return best


def _is_aggregate(sql: str) -> bool:
    return bool(_AGG_RE.search(sql))


def _build_chart(columns: list[str], rows: list[list]) -> dict | None:
    """Emit a simple bar-chart spec when the shape is (label, number)."""
    if len(columns) != 2 or not rows:
        return None
    numeric = all(isinstance(r[1], (int, float)) for r in rows)
    if not numeric:
        return None
    return {
        "type": "bar",
        "x_label": columns[0],
        "y_label": columns[1],
        "points": [{"label": str(r[0]), "value": float(r[1])} for r in rows[:20]],
    }


class QueryPilot:
    """Stateful orchestrator. Holds recent history and pending (awaiting-approval) queries."""

    def __init__(self) -> None:
        self._pending: dict[str, QueryState] = {}
        self._history: list[QueryState] = []

    # -- public API ---------------------------------------------------------
    def ask(self, question: str) -> QueryState:
        settings = get_settings()
        state = QueryState(id=uuid.uuid4().hex[:12], question=question)

        # 1. retrieve schema (grounding)
        with Timer() as t:
            tables = [tbl["table"] for tbl in schema_as_dict()]
        state.trace.append(TraceStep("retrieve_schema", "ok", t.ms, f"{len(tables)} tables"))

        # 2. generate SQL
        with Timer() as t:
            gen: Generation = get_provider().generate(question)
        state.provider = gen.provider
        state.rationale = gen.rationale
        state.confidence = gen.confidence
        state.sql = gen.sql
        if not gen.sql:
            state.trace.append(TraceStep("generate_sql", "fail", t.ms, gen.rationale))
            state.status = "rejected"
            self._record(state)
            return state
        state.trace.append(TraceStep("generate_sql", "ok", t.ms, f"{gen.provider} (conf {gen.confidence:.2f})"))

        # 3. validate (hard safety boundary)
        with Timer() as t:
            v = validator.validate(gen.sql)
        if not v.ok:
            state.trace.append(TraceStep("validate", "fail", t.ms, v.reason))
            state.status = "rejected"
            state.rationale = f"Blocked by validator: {v.reason}"
            self._record(state)
            return state
        state.tables = list(v.tables)
        state.safe_sql = validator.ensure_limit(gen.sql, settings.max_rows)
        state.trace.append(TraceStep("validate", "ok", t.ms, f"read-only SELECT over {list(v.tables)}"))

        # 4. guard (governance policy + cost estimate)
        with Timer() as t:
            state.estimated_rows = _estimate_rows(state.tables)
            aggregate = _is_aggregate(state.safe_sql)
            risky = (not aggregate) or (state.estimated_rows > settings.approval_row_threshold)
        reason = (
            "aggregate query within limits"
            if not risky
            else ("row-level data access" if not aggregate else "large scan estimate")
        )
        state.trace.append(TraceStep("guard", "pending" if risky else "ok", t.ms, reason))

        if risky:
            state.status = "needs_approval"
            self._pending[state.id] = state
            self._record(state)
            return state

        return self._execute(state)

    def approve(self, query_id: str) -> QueryState:
        state = self._pending.pop(query_id, None)
        if state is None:
            raise KeyError(query_id)
        state.trace.append(TraceStep("approval", "ok", 0.0, "approved by human"))
        return self._execute(state)

    def reject(self, query_id: str) -> QueryState:
        state = self._pending.pop(query_id, None)
        if state is None:
            raise KeyError(query_id)
        state.status = "rejected"
        state.rationale = "Rejected by human reviewer."
        state.trace.append(TraceStep("approval", "fail", 0.0, "rejected by human"))
        return state

    def history(self, limit: int = 25) -> list[QueryState]:
        return list(reversed(self._history[-limit:]))

    # -- internals ----------------------------------------------------------
    def _execute(self, state: QueryState) -> QueryState:
        with Timer() as t:
            try:
                cols, rows = warehouse.run_select(state.safe_sql, limit=get_settings().max_rows)
                state.columns, state.rows = cols, rows
                state.chart = _build_chart(cols, rows)
                state.status = "completed"
                status = "ok"
                detail = f"{len(rows)} row(s)"
            except Exception as exc:  # noqa: BLE001
                state.status = "error"
                state.rationale = f"Execution error: {exc}"
                status = "fail"
                detail = str(exc)
        state.trace.append(TraceStep("execute", status, t.ms, detail))
        if state.status == "completed":
            state.trace.append(TraceStep("format", "ok", 0.0, "chart" if state.chart else "table"))
        self._record(state)
        return state

    def _record(self, state: QueryState) -> None:
        self._history.append(state)
        self._history = self._history[-200:]


pilot = QueryPilot()
