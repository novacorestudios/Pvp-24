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


Milestone 10F: 318 local pytest tests passed with Ruff format/lint and provenance checks. Focused command: `.venv/bin/python -m pytest -q tests/test_paper_venue_actions.py tests/test_paper_venue.py` (17 tests). Synthetic fixtures explicitly freeze a one-second LAST freshness limit and fee inputs; these are not production defaults. A temporary test-edit placement error was caught by Ruff and corrected before the passing run. No live orders, historical data or operational Freqtrade process has run.


Milestone 10G: 322 local pytest tests passed with Ruff format/lint and provenance checks. Focused command: `.venv/bin/python -m pytest -q tests/test_reconcile_pending_batch.py` (4 tests). `.venv/bin/python scripts/smoke_reference.py --output artifacts/reference-smoke-10g` also passed; use a new output directory on repeat. It still delivers 964 events with trace hash `14d443af600ab971927ef90121ba9acf49ca62645c73c21cb44dbdd1fdb5f6f0`, restart verified and zero external orders. Outputs remain synthetic integration evidence, not historical performance.


Milestone 10H: 333 local pytest tests passed with Ruff format/lint and provenance checks. Focused command: `.venv/bin/python -m pytest -q tests/test_paper_session.py` (11 cases). Recovery fault injection covers both independent commit boundaries, durable source anchors, absent lookups and bounded pages. Tests explicitly use a socket-free PRELIMINARY model; no operational PAPER, historical performance or exchange order is claimed.


Milestone 10I: 342 local pytest tests passed with Ruff format/lint and provenance checks. Focused command: `.venv/bin/python -m pytest -q tests/test_paper_pump.py` (9 cases). The actual pinned framework command `.deps/freqtrade/.venv/bin/python scripts/smoke_freqtrade_parity.py` also passed; log: artifacts/freqtrade-parity-m10i-final.log. It now checks six modeled requests and two fills per path through replacement/cancel/exit, with execution evidence hash `f434633cf4dfef2025708f646550502946fc62e1f85a924c948399206190baa1` and zero external orders. The fixture contract tick is 0.01 to support its 101.21 price; the updated fixture intent hash is `30182c81e794ccc4d112c4c8bc9c4ef9eca4364ddee68969be0e593c178f2129`. Runtime interpreter links were repaired before a successful locked bootstrap (`python scripts/bootstrap_freqtrade.py --install`); generated dependency files are not committed. This executes the real strategy loader/callbacks with a local model, not full operational FreqtradeBot startup or historical performance.


Milestone 10J: 349 local pytest tests passed with Ruff format/lint and provenance checks. Focused command: `.venv/bin/python -m pytest -q tests/test_paper_watchdog.py` (7 cases). `.deps/freqtrade/.venv/bin/python scripts/smoke_freqtrade_parity.py` passed with real strategy cleanup/reinstantiation and active-stop recovery; log artifacts/freqtrade-parity-m10j.log. The explicitly synthetic acknowledgement policy is one second, frozen before dispatch; no production timeout is inferred. Execution evidence hash remains `f434633cf4dfef2025708f646550502946fc62e1f85a924c948399206190baa1`. This remains offline strategy/model parity, not a full operational FreqtradeBot process.


Milestone 10K: `.deps/freqtrade/.venv/bin/python scripts/smoke_freqtrade_parity.py --framework` passed, exercising real FreqtradeBot initialization/startup/three process cycles/cleanup with a strict offline exchange fixture and prohibited socket/DNS access. Log: artifacts/freqtrade-framework-m10k.log. The ordinary parity command also passed (artifacts/freqtrade-parity-m10k.log). Both keep execution evidence hash `f434633cf4dfef2025708f646550502946fc62e1f85a924c948399206190baa1`. Production core remains unchanged from the 349-test passing suite; Ruff/provenance pass. CI now executes both modes. Empty native-candle warnings are intentional: all normalized synthetic data enters the shared core. No public market feed or operational PAPER readiness is claimed.


## Milestone 11A official archive sample

374 tests passed with Ruff format/lint and provenance verification. The acquisition command below completed successfully, fetching public data only and submitting zero orders:

```bash
.venv/bin/python scripts/acquire_binance_archives.py --symbol BTCUSDT --month 2024-01 --output data/acquisition-11a-final
```

All five archives were acquired and reconsumption integrity checks passed. Exact source URLs, checksums, coverage, decoder/acquirer hashes, base commit, dirty-worktree flag and dataset hash are in docs/data/11a-source-manifest.json. The CLI prints the immutable report path. Existing identical ZIPs are cached; checksum retrieval remains fresh, and changed revisions are retained separately. Failed attempts remain auditable. Raw data is ignored by Git; no network acquisition runs in CI.

The first ingestion attempt deliberately remains recorded locally as 4/5: raw funding timestamp jitter invalidated the initial continuous-interval interpretation. The corrected decoder retains the raw declared interval and actual timestamp, records 28 discrepancies and refuses to attest continuous funding coverage. Final successful reports contain 5/5 files; this is not strategy performance. No historical universe/rules or L2 has been acquired. Final Test months are rejected before any download.


## Milestone 11B causal normalization

386 tests passed with Ruff format/lint and provenance checks. The exact committed 11A dataset can be audited after acquiring its pinned source objects:

```bash
.venv/bin/python scripts/audit_archive_dataset.py \
  --root data/acquisition-11a-final \
  --manifest docs/data/11a-source-manifest.json \
  --dataset-hash 985453a92d0283cd4fd6fc60b55296bfe65110b7c8f07baa99ffda3d280bb0a6 \
  --symbol BTCUSDT --month 2024-01 \
  --output artifacts/normalization-11b
```

This command completed successfully: 744 LAST hours, 744 Mark hours, 31 derived UTC daily LAST observations and no missing intervals in the sample. The normalization hash is `a7af2112f560a461015b016fe3d80d7ad1efae761efb1f94765a4f65ccd5c60a`. See docs/data/11b-normalization-summary.json for implementation hashes and the honestly dirty local source state. Different retrieval attempt timestamps create new attempt IDs; the committed manifest deliberately refers to its original attempts, so preserve those attempt records or explicitly review a newly acquired manifest with matching dataset identity. Do not silently substitute an attempt or source revision.

Twelve additional tests cover explicit hash pins, metadata/object tampering, duplicate or failed revisions, locked Final and missing months, availability boundaries, complete-day requirements, LAST/Mark separation, late corrections, future-append invariance and ambiguous/off-grid inputs. No strategy backtest or operational PAPER process was run.


## Milestone 11C official source inventory

400 tests passed with Ruff format/lint and provenance verification. This read-only metadata command completed successfully:

```bash
.venv/bin/python scripts/inventory_binance_archives.py --output data/catalog-11c
```

It enumerated 8 monthly kinds, 9 daily kinds and 1018 monthly kline symbol directories (two pages), fetching four XML directory pages and zero archive objects. Raw evidence and exact implementation hashes are committed in docs/data/11c-catalog-pages and docs/data/11c-source-inventory.json. Reruns may observe a changed directory inventory; preserve the existing checkpoint rather than overwriting historical observations. Fourteen new tests verify complete pagination, token encoding/identity, failed/truncated/repeated pages, resource boundaries, response identity, refusal of leaf/date paths and retention of prior evidence.
