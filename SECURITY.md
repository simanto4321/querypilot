# Security Policy

## Reporting a vulnerability

Email **msimanto46@gmail.com** with details. Please do not open a public issue for
security-sensitive reports.

## Threat model & safeguards

QueryPilot assumes the NL→SQL layer (especially an LLM) is **untrusted** and can
be manipulated via prompt injection. Safety therefore does not depend on the model:

- **Deterministic validation:** `sqlglot` AST inspection enforces a single
  read-only `SELECT` over whitelisted tables. DML/DDL, stacked statements,
  `PRAGMA`, `ATTACH`, and file functions are rejected.
- **Bounded execution:** every query gets an enforced `LIMIT`; the DB connection
  is read-only (use a read-only role in production).
- **Human-in-the-loop:** row-level or large-scan queries require explicit approval.
- **Secrets:** configuration is env-driven (`QUERYPILOT_*`); `.env` is git-ignored.

The test suite includes injection-style payloads to continuously verify these
guarantees.
