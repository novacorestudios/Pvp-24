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

Milestone 3: 53 tests passed, including future-append invariance for candles and historical universe, missing-day rejection, zero/missing distinction, Last/Mark separation, 30-day gap recovery, and inclusive 30/90-second deadlines. Data fixtures are explicitly synthetic. No historical performance run.

Milestone 4: 68 tests passed using the same commands. Signal fixtures test strict price thresholds, inclusive RVOL threshold, previous ATR vs current ATR, no repeat transition after low-volume rejection, long/short symmetry, future-append invariance, complete batch ranking, deadline behavior and indicator checkpoint restart parity.

Milestones 5A/5B/6A/6B: the same lint/test commands passed with 85/103/116/129 tests respectively. Coverage includes causal funding, exact risk/cost boundaries, tier-consistent synthetic liquidation, concurrent reservation/intent atomicity, book sequencing/consumption, IOC caps, partial fills, cancel/fill races, protection acknowledgements and transactional restart behavior. These are code tests, not actual exchange fixture validation or historical performance evidence.
