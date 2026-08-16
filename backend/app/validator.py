"""Read-only SQL validation using sqlglot AST inspection.

This is the core safety boundary: no matter what the NL layer (deterministic or
LLM) produces, a query only runs if it is a single, read-only SELECT over
whitelisted tables. Everything else is rejected before touching the database.
"""
from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from .catalog import ALLOWED_TABLES

# Statement types that must never be executed.
_FORBIDDEN = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter,
    exp.TruncateTable, exp.Merge, exp.Command,
)


@dataclass
class ValidationResult:
    ok: bool
    reason: str = ""
    tables: tuple[str, ...] = ()


def validate(sql: str) -> ValidationResult:
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        return ValidationResult(False, "empty query")

    # Reject stacked statements outright (defense in depth beyond the parser).
    try:
        statements = sqlglot.parse(sql, read="sqlite")
    except Exception as exc:  # noqa: BLE001
        return ValidationResult(False, f"could not parse SQL: {exc}")

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        return ValidationResult(False, "only a single statement is allowed")

    tree = statements[0]

    # The top-level node must be a SELECT (or a parenthesized/CTE select).
    if not isinstance(tree, (exp.Select, exp.Subquery, exp.Union)) and not (
        isinstance(tree, exp.Expression) and tree.find(exp.Select)
    ):
        return ValidationResult(False, "only SELECT queries are allowed")

    # Absolutely no write/DDL nodes anywhere in the tree.
    for node in tree.walk():
        if isinstance(node, _FORBIDDEN):
            return ValidationResult(False, f"forbidden statement: {type(node).__name__.lower()}")

    # Block DELETE/DROP smuggled via function or unknown commands already covered;
    # also reject PRAGMA / ATTACH style commands parsed as anonymous.
    lowered = sql.lower()
    for banned in ("pragma", "attach ", "; --", "into outfile", "load_file"):
        if banned in lowered:
            return ValidationResult(False, f"blocked keyword: {banned.strip()}")

    # Every referenced table must be in the whitelist.
    referenced = {t.name for t in tree.find_all(exp.Table)}
    unknown = referenced - ALLOWED_TABLES
    if unknown:
        return ValidationResult(False, f"unknown/forbidden table(s): {sorted(unknown)}")
    if not referenced:
        return ValidationResult(False, "query references no known tables")

    return ValidationResult(True, tables=tuple(sorted(referenced)))


def ensure_limit(sql: str, max_rows: int) -> str:
    """Return the SQL with an enforced LIMIT (never larger than max_rows)."""
    sql = sql.strip().rstrip(";").strip()
    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
    except Exception:  # noqa: BLE001
        return f"SELECT * FROM ({sql}) AS _q LIMIT {max_rows}"

    limit_node = tree.args.get("limit")
    if limit_node is not None:
        try:
            current = int(limit_node.expression.name)
            if current <= max_rows:
                return tree.sql(dialect="sqlite")
        except (AttributeError, ValueError):
            pass
    return tree.limit(max_rows).sql(dialect="sqlite")
