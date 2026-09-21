# M11V — Partial historical security/rule evidence compiler

## Scope

M11V is a historical metadata/provenance milestone only. It does not change PVB-24 Alpha,
signal thresholds, risk fractions, leverage, sizing, entry/exit behavior, execution rules,
funding logic, baseline configuration, or Final Test governance.

The milestone adds a fail-closed compiler that joins already-retained official Binance evidence:
- M11T announcement-body qualification V3;
- M11T lifecycle/archive reconciliation V3;
- M11F reviewed tick-size change evidence.

It does **not** use current exchangeInfo as historical truth and does not infer missing contract
rules from today's values.

## Code checkpoint

Code checkpoint before documentation:
`c26760873b0393d49a62639579206eef326072b5`.

PVB-24 CI Actions **35647746659 / #143 — SUCCESS**:
- Ruff format: passed;
- Ruff lint: passed;
- pytest: passed;
- provenance verification: passed;
- reference smoke: passed;
- Freqtrade smoke/parity/framework parity: passed.

The implementation scope is limited to:
- `src/pvb24/data/historical_metadata_evidence.py`;
- `scripts/compile_historical_metadata_evidence.py`;
- `tests/test_historical_metadata_evidence.py`;
- `.github/workflows/m11v-historical-metadata-evidence.yml`.

No strategy/risk/execution/frozen-config file changed.

## Evidence workflow

M11V evidence workflow Actions **35648265777 / run #4 — SUCCESS**.

The workflow restored the exact pinned M11T reports:
- qualification report SHA-256:
  `ed5539a48c6fca0fca16823bfd4dfd60ad3048c57716635adbb5d04d4b5ddd3a`;
- lifecycle reconciliation report SHA-256:
  `2c935625dffef3a949b7b30c4dfb55ca75b6b78c70771958d710c6925a0253bd`;
- committed M11F tick evidence SHA-256:
  `1a14deb4eb7a4191c9f15d7b510c66bb762ea56b2553ea869b99b97e5bc69dbd`.

The exact generated report is committed at:
`docs/data/11v-historical-metadata-evidence.json`

Report SHA-256:
`8130ae8d57cb60747daaef379a1713a990937d499a86360c920d0584a7e20252`

Internal evidence hash:
`4794c5f0fb40ef343523d56744c6e7a9e9fa7b24fcdd22879df7f7af078bc26d`

The report was captured byte-for-byte from the successful workflow artifact.

## Actual result

The compiler found:

- consistent preliminary listing candidates: **15**;
- unresolved listing boundaries retained as UNKNOWN: **7**;
- delisting events retained as event evidence: **11**;
- USDT tick-size field events: **10**;
- full Security rows emitted: **0**;
- full ContractRules rows emitted: **0**.

Consistent listing candidates:
AVAXUSDT, DEFIUSDT, DOTUSDT, ENJUSDT, FILUSDT, FLMUSDT, FTMUSDT, HNTUSDT, KSMUSDT, MKRUSDT, OCEANUSDT, RENUSDT, TOMOUSDT, UNIUSDT, YFIUSDT.

UNKNOWN listing boundaries:
BLZUSDT, DOTUSDT, MATICUSDT, NEARUSDT, SNXUSDT, STORJUSDT, WAVESUSDT.

Delisting-event symbols:
ANTUSDT, BLUEBIRDUSDT, BONDUSDT, CTKUSDT, DGBUSDT, FOOTBALLUSDT, LOOMUSDT, MAVIAUSDT, OMGUSDT, ORBSUSDT, XEMUSDT.

USDT tick-field symbols:
AEVOUSDT, AUCTIONUSDT, CFXUSDT, ONGUSDT, RADUSDT, RDNTUSDT, RONINUSDT, STEEMUSDT, USDCUSDT, VETUSDT.

Two non-USDT tick rows remain excluded from the USD-M/USDT rule set:
SUIUSDC, WLDUSDC.

## Causal protections

A listing candidate is materialized only when:
- the announcement body was independently qualified;
- its exact retained source revision matches lifecycle reconciliation;
- the event timestamp matches the qualified fact;
- the fact was causally available before the event, except an explicitly handled postponement
  revision whose semantics are retained rather than retroactively rewriting the old event;
- the lifecycle boundary is `CONSISTENT_EVENT_BOUNDARY_ONLY`.

The seven UNKNOWN listing boundaries are never converted to Security rows.

Every emitted preliminary Security candidate deliberately carries:
- `classification="UNKNOWN"`;
- `historical_verified=false`.

Therefore it remains ineligible for PVB-24 universe admission until independent classification
evidence exists.

Tick-size changes remain field-level rule evidence only. M11V does not manufacture a complete
`ContractRules` snapshot from a tick change.

## Explicit remaining gaps

The committed result deliberately remains:

- `classification_complete=false`;
- `security_change_stream_complete=false`;
- `security_history_complete=false`;
- `contract_rule_history_complete=false`;
- `historical_universe_complete=false`;
- `liquidation_tiers_complete=false`;
- `quality=PRELIMINARY`;
- `operational_ready=false`;
- `live_enabled=false`;
- Final Test `LOCKED`.

Mandatory rule gaps remain:
- `QUANTITY_STEP`
- `MIN_QUANTITY`
- `MAX_QUANTITY`
- `MIN_NOTIONAL`
- `CONTRACT_SIZE`
- `MAINTENANCE_TIERS`
- `ORDER_CAPABILITIES`
- `LAST_STOP_CAPABILITY`

This means M11V closes the **compiler and evidence-binding problem**, not the complete historical
Security Master / Universe / Contract Rules capability.

## What is still required

Historical universe promotion still requires independent, causally usable evidence for:
- crypto/stable/non-crypto classification as known at each decision;
- a complete security change stream, including listing/delisting/rename/relisting coverage;
- historical quantity-step, min/max quantity and minimum-notional changes;
- contract-size semantics where applicable;
- order capability and LAST-stop capability history;
- leverage/maintenance-margin tiers and liquidation-rule history.

Current rules must not be substituted for missing historical revisions.

The 11M readiness gate therefore remains blocked. No historical performance result is promoted,
PAPER remains NOT READY, LIVE remains DISABLED, and Final Test remains LOCKED.
