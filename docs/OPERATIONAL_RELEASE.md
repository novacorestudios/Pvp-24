# PVB-24 Operational Release Boundary

## Status

This document closes the operational-runtime engineering lane only. It does **not**
promote PAPER readiness, unlock the Final Test, authorize historical performance,
or enable LIVE trading.

Current immutable governance remains:

- branch: `build/pvb24-v1`
- LIVE: disabled
- PAPER readiness: false
- Final Test: locked
- historical performance: blocked until the historical readiness gate passes
- execution transport in the committed PAPER config: `BLOCKED_UNTIL_QUALIFIED`
- no trading credentials are permitted in the committed PAPER config

## Required preflight

Every candidate checkout must pass:

```bash
python scripts/verify_provenance.py
python scripts/check_operational_package.py
python -m ruff format --check .
python -m ruff check .
python -m pytest -q
```

GitHub Actions runs these controls on the branch. A failed control is a release
blocker; do not bypass or weaken it.

The operational preflight verifies the frozen strategy configuration hash, PAPER
mode, UTC timebase, Freqtrade pin, strategy/executor selection, frozen execution
controls, manifest provenance, disabled LIVE state, blocked transport, and
unpromoted PAPER readiness.

## Runtime startup order

1. Construct `OperationalRuntime` with the pinned PAPER configuration and durable
   journal/scope.
2. Start the runtime.
3. If the explicitly authorized local PRELIMINARY L2 research transport is used,
   bind it without changing LIVE/PAPER governance.
4. Complete execution recovery before account reconciliation.
5. Bind an explicit `ReconciliationPolicy` with finite nonnegative freshness
   limits and the required quality mode.
6. Reconcile the account/owned-position observation.
7. Permit strategy cycles and new entry submission only when
   `entry_gate_ready=true`.

A reconciliation failure or unresolved account state keeps strategy cycles and
new entries fail-closed.

## Safety traffic while entries are paused

The reconciliation entry gate must **not** stop the system from becoming safer.
While new entries are blocked:

- fresh evidence delivery remains allowed;
- durable execution recovery remains required;
- protective/exit action pumping remains allowed;
- foreign positions remain outside PVB-24 ownership and must not be mutated.

This separation prevents a closed entry gate from deadlocking protection or
state recovery.

## Restart and shutdown

On restart, execution recovery must finish before reconciliation and before new
strategy operation. Unresolved execution remains blocked and must be reconciled
by durable client identity/evidence rather than blind resend.

Shutdown is idempotent. Closing the runtime resets recovery and reconciliation
readiness; a later process must establish both again.

## Release rule

An operational-runtime checkpoint is acceptable only when the exact branch HEAD
has a successful PVB-24 CI run with governance, Freqtrade smoke, and evidence
dispatch gates satisfied as applicable.

Passing this release boundary is an engineering property, not evidence that the
strategy is profitable or that PAPER/LIVE deployment is authorized.
