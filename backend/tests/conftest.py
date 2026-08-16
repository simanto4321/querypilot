"""Isolated SQLite warehouse per test session, seeded before app imports."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP = tempfile.mkdtemp(prefix="querypilot_test_")
os.environ["QUERYPILOT_WAREHOUSE_URL"] = f"sqlite:///{(Path(_TMP) / 'test.db').as_posix()}"


@pytest.fixture(scope="session", autouse=True)
def seeded():
    from app.warehouse import seed

    seed()
    yield
