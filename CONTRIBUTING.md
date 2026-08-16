# Contributing

## Setup

```bash
cd backend && python -m venv .venv && pip install -r requirements.txt
python -m app.warehouse && pytest -q

cd frontend && npm install && npm run build
```

## Guidelines

- **Never weaken the validator.** Any change to `validator.py` must keep every
  test in `tests/test_validator.py` passing, including the injection payloads.
- New NL intents go in `providers.py` with a matching test in `tests/test_agent.py`.
- All SQL execution stays read-only and bounded by `ensure_limit`.
- Run `pytest -q` and `npm run build` before opening a PR.
