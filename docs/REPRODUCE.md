# Tested reproduction commands

Working directory: repository root; Python 3.12.14. All commands below completed with exit code 0.

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]' --disable-pip-version-check
.venv/bin/python scripts/bootstrap_freqtrade.py --install
.venv/bin/python -m ruff format --check .
.venv/bin/python -m ruff check .
.venv/bin/python -m pytest -q
.venv/bin/python scripts/verify_provenance.py
.deps/freqtrade/.venv/bin/python scripts/smoke_freqtrade.py
```

16 tests passed at Milestone 1. Freqtrade 2026.8 configuration loaded with dry_run=true and zero submitted orders. Bootstrap verifies the official source SHA and uses the recorded Python 3.12 package lock; no automatic upgrade. Native Linux path conventions are used.

Initial official installation used the pinned requirements.txt then pip install -e . inside a separate venv. A repeat install through bootstrap_freqtrade.py passed using the derived exact dependency lock. The script follows the pinned official manual-install sequence.

No backtest or operational paper-start command has run. No static type checker is configured yet.

Development failures, resolved: smoke attempted before install finished; missing smoke user-data directory; disabled Telegram object still required token fields. The final smoke creates its isolated directory and omits optional Telegram/API-server objects. No credentials were supplied.

Milestone 2: same lint/test commands passed with 35 tests, including a subprocess crash recovery test and concurrent order-dispatch claiming.
