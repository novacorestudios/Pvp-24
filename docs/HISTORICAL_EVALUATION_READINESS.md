# Historical evaluation readiness gate — current fail-closed state

## Post-audit remediation status — 2026-09-22

The engineering audit remediation F1–F10 is complete, but it did **not** promote
historical-data coverage or operational readiness.

The authoritative frozen matrix remains
`docs/data/11m-pre-final-readiness.json`. Its current top-level state is:

- `final_test_access=LOCKED`
- `performance_run=false`
- `operational_ready=false`
- all eleven mandatory capabilities remain `PARTIAL`.

The current partial capabilities are HISTORICAL_UNIVERSE, SECURITY_MASTER,
CONTRACT_RULES, LIFECYCLE, LAST_1H, LAST_1M, MARK_1M,
FUNDING_SETTLEMENT_PRICING, FUNDING_SCHEDULE, FUNDING_RESERVE and
LIQUIDATION_RULES.

Later audit work materially improved evidence integrity — durable source
preservation, replayability, same-SHA CI qualification, delisting-revision
semantics, symbol/timezone binding and per-source point-in-time availability —
but none of those controls proves full 2020-01-01 through 2025-06-30 capability
coverage. They therefore must not be interpreted as permission to run or publish
historical performance.

The readiness gate remains authoritative. A performance run is allowed only when:

```bash
python scripts/check_historical_evaluation_readiness.py
```

exits successfully. Until then, Final Test stays LOCKED, PAPER stays NOT READY and
LIVE stays DISABLED.

---

## Original Milestone 11M gate design retained below

PVB-24 now has a hard precondition between historical source qualification and any
strategy performance run. The gate covers the frozen Development + Validation
window from 2020-01-01 through 2025-06-30; the Final Test boundary remains
2025-07-01 and stays locked.

The current matrix is `docs/data/11m-pre-final-readiness.json`. It pins the exact
Git blob identity of every evidence file it uses and applies semantic checks to
stable source/report identities. A changed evidence file, changed schema, failed
semantic anchor, duplicated capability, path traversal, widened time window, or
attempt to unlock Final Test fails closed.

Eleven capabilities are mandatory before a pre-Final performance run:

- historical causal universe;
- security master;
- contract rules;
- lifecycle/delisting coverage;
- LAST 1h;
- LAST 1m;
- Mark 1m;
- funding settlement pricing;
- funding schedule;
- 30-day funding reserve coverage;
- liquidation/maintenance rules.

A capability can be `MISSING`, `PARTIAL` or `COMPLETE`. MISSING and PARTIAL
always block performance. COMPLETE cannot be asserted directly from an arbitrary
source report: it requires a dedicated
`PVB24_CAPABILITY_ATTESTATION_V1` covering the entire frozen pre-Final interval,
with no remaining gaps and explicit PRELIMINARY or VERIFIED quality.

This distinction is intentional. A one-month BTCUSDT archive can prove that the
decoder and causal normalization work for that month, but it cannot authorize a
six-year universe backtest. Likewise, 93 exact January-2024 funding rows do not
prove a complete funding calendar.

Run the audit with:

```bash
python scripts/check_historical_evaluation_readiness.py
```

Exit code 0 means every mandatory capability is COMPLETE. Exit code 2 means the
performance run is blocked and the JSON output lists the blocking capabilities.
The function `require_performance_ready()` is the mandatory programmatic guard
for future historical performance runners.

At Milestone 11M the committed matrix is expected to be blocked: all eleven
capabilities remain PARTIAL. This is a governance success, not a strategy failure.
It prevents incomplete data from becoming a misleading P&L result.

The gate does not change Alpha, thresholds, sizing, leverage or execution rules.
It does not open Final Test and does not imply PAPER or LIVE readiness.
