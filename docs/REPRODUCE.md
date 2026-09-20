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

Milestone 7: 146 tests passed with the same commands, including symmetrical long/short exit boundaries, close-only MFE, late/proposed stop timing, no widening, gaps, exact 72-hour hold time and exit-state checkpoint replay.

Milestone 8A: 164 tests passed, including long/short fill accounting, partial emergency exit allocation, fee/funding deduplication, late-fill reconciliation, Mark freshness/as-of invariance, liquidation visibility, durable ledger recovery and exact daily/drawdown boundaries. No historical performance or exchange fixture validation has run.

Milestone 8B: 172 tests passed with the same commands. Added atomic account/protection rollback, entry blocking after fill/funding, terminal zero-fill release, late-fill reblocking, cash/flatness proof, no backdated reconciliation and preservation of safety pauses after full exit.

Milestone 8C: 181 tests passed. Residual-position tests cover exact largest-step buffer repair, reduction fees, adverse fills, funding debits, proportional collateral release, fixed original stop and fail-closed unknown/UNVERIFIED projections.

Milestone 8D: 187 tests passed. Added durable risk-policy initialization, entry-vs-protection dispatch gating, atomic drawdown close/cancel intents, no unknown-close resubmission, additional closure of late confirmed quantity, pre-dispatch cancellation and risk-service restart recovery.

Milestone 8E: 199 tests passed with the same commands. Coverage includes owned open-account cash/quantity proof, stale and future evidence rejection, current-minute risk gating, actual-fill risk freezing, confirmed partial-exit risk release, unchanged initial risk after acknowledged trailing, pending close deduplication, quality labels and post-fill compliance failure.

Milestone 9A: 212 tests passed. New tests cover availability-first replay, sequence domains, conservative ambiguity counting, deterministic reordered/future-appended input, fail-closed callback errors, explicit quality rejection, first post-decision minute opens, deadline/participation bounds, LAST/Mark separation, adverse intrabar ambiguity, gap stops and exclusion of pre-fill/pre-ack extrema.

Milestone 9B: 224 tests passed. Integrated tests cover account restart receipts, fault injection after nested fill writes, shared Mark/funding/equity, dispatched-intent acknowledgements, continuous 72h hold, shared hourly ATR/early failure, concurrent risk/exit close deduplication, partial terminal closure, missing fill evidence, visible liquidation accounting and savepoint rollback.

Milestone 9C: 234 tests passed. Added ranked sequential slot/risk allocation, atomic ownership rollback, restart-identical planning, deadline/current-risk/future-input rejection, preliminary price-bound enforcement, shared signal parity, pending ownership blocking, missing-batch deadline and quality isolation.

Milestone 9D: 240 tests passed. Added full synthetic lifecycle with restart and exact cash identity, adverse tick rounding, unknown-dispatch nonresubmission, gap rejection without fee/cooldown, account-gate cancellation, atomic synthetic commit failure and immutable proxy inputs.

Milestone 9E: 246 tests passed. Added preliminary account observation into open reconciliation, partial-exit collateral accounting, immutable model policy, adverse gap-stop execution, visible liquidation loss/fees/ambiguity with deduplication, and refusal to infer an intrabar protection path.

Milestone 9F: 248 tests passed, including full-run future-append invariance and protection of prior output evidence. The following command was executed successfully (use a new output directory on repeat):

```bash
.venv/bin/python scripts/smoke_reference.py --output artifacts/reference-smoke-9f-final
```

It delivered 964 synthetic events, verified account restart and sent zero exchange orders. Trace hash: `14d443af600ab971927ef90121ba9acf49ca62645c73c21cb44dbdd1fdb5f6f0`. Files: manifest.json, synthetic-events.jsonl, trace.jsonl, summary.json, account.sqlite. The successful local implementation run accurately reports worktree_dirty=true; clean CI runs record their exact committed source. These artifacts are reproducible integration evidence, not historical performance reports.

Milestone 10A: 258 local pytest tests passed. The actual pinned Freqtrade environment also passed:

```bash
.deps/freqtrade/.venv/bin/python scripts/smoke_freqtrade_parity.py
```

It loaded PVB24Executor and confirmed event/signal/intent parity with zero submitted orders. Signal hash: `fc7ef7cbb1f1dd764f48352ecf24b03172f2572977af7f897c7814e2af8f5363`; intent hash: `73059e20035fe209b1adb8d98677d30dd14ccc05fecd60ed14639c64050ba24c`. Logs: artifacts/freqtrade-parity-m10a.log and artifacts/freqtrade-bootstrap-m10a-repair.log. The first local attempt failed because the copied dependency virtualenv's Python link was broken; after repairing the generated interpreter link, locked bootstrap and parity succeeded. No unexecuted live/dry-run trading startup is claimed.


Milestone 10B: 280 local pytest tests passed with Ruff format/lint and provenance checks. The focused command is `.venv/bin/python -m pytest -q tests/test_paper_dispatch.py` (22 tests). These are synthetic PAPER transport-contract tests: write-ahead visibility is checked through a separate SQLite connection, and lost response/restart cases never resend or release reservations. No concrete operational backend or native Freqtrade order path is enabled.


Milestone 10C: 288 local pytest tests passed with Ruff format/lint and provenance checks. Focused command: `.venv/bin/python -m pytest -q tests/test_paper_actions.py tests/test_paper_dispatch.py` (30 tests). The action fixtures feed confirmed entries and stop acknowledgements through AccountReplay while the backend remains explicitly synthetic. No operational PAPER start or external order submission is claimed.


Milestone 10D: 301 local pytest tests passed with Ruff format/lint and provenance checks. Focused command: `.venv/bin/python -m pytest -q tests/test_paper_evidence.py` (13 tests). A first lifecycle fixture accidentally assigned entry and exit the same event time without comparable venue sequences; the ledger correctly rejected that ambiguous reduction-before-entry case. The fixture was corrected to record exit later, preserving the core ordering policy. Test helper lint and a liquidation-count assertion name were corrected before the final full pass. No historical performance, real exchange fixture validation or operational PAPER run is claimed.


Milestone 10E: 309 local pytest tests passed with Ruff format/lint and provenance checks. Focused command: `.venv/bin/python -m pytest -q tests/test_paper_venue.py` (8 tests). A concrete socket-free PRELIMINARY L2 model uses a separate durable SQLite database, explicit fixture book/fee/rule inputs and journaled order/fill evidence. It models entry only at this checkpoint. No historical dataset, native exchange order or operational Freqtrade trading run is claimed.
