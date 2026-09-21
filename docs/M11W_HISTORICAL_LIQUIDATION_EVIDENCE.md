# M11W — Historical liquidation / maintenance-tier evidence

## Scope

M11W is a data/provenance and liquidation-rule evidence milestone only.

It does **not** change:
- PVB-24 Alpha or signal thresholds;
- risk fractions, sizing, leverage policy or the mandatory 3R liquidation buffer;
- entry/exit logic;
- funding logic;
- execution strategy;
- frozen baseline/reference configuration;
- Final Test governance.

The milestone qualifies retained official Binance USD-M leverage/margin-tier announcements and
records exactly what they prove. Missing maintenance-amount/cum evidence is not reconstructed
from today's API or from an assumed formula and no historical `ContractRules` object is emitted.

## Implementation checkpoints

The source-probe path was finalized through:
`4955c232a83d4da92ad200ca27d20e65db8a0be8`.

M11W source-probe workflow:
- Actions `35650220174`, run #4 — **SUCCESS**;
- artifact: `m11w-margin-tier-source-probe`;
- artifact ZIP digest:
  `3d3c21c8dd0c2544fa91c7d9b36353b64b116a8e413ba675de816b2ac00961e0`.

The historical tier compiler was finalized at:
`bd664c3bdcae46a79191132337cacb2ed9a3c335`.

PVB-24 CI `35651486792` / #155 — **SUCCESS**.

The pinned evidence workflow was added at:
`5d200a7f9996b00f8b250551e940ab9b819338b9`.

PVB-24 CI `35651722332` / #156 — **SUCCESS**.

The exact-report capture checkpoint is:
`24189315b9c65161a0a43056ecff68e0291b4586`.

No strategy/risk/execution/frozen-config file was changed by M11W.

## Pinned official source evidence

Three retained official Binance CMS revisions were selected. Each source is pre-Final and was
re-hashed from retained raw bytes before compilation.

### 1. BTCUSDT / ETHUSDT tier update

Article code:
`aa735cd2d8bd4e7bb092179cf086e486`

- published: `2024-05-27T06:00:01.615000Z`;
- effective: `2024-05-28T10:30:00.000000Z`;
- timing: `ANNOUNCED_BEFORE_EFFECTIVE`;
- existing positions opened before the update: **not affected**;
- source SHA-256:
  `3bff04afbfd0d508fd88ba3398e898dd8fa05e1c66cc8c6e3d833e044eef6e46`;
- body SHA-256:
  `680d82b5f9c7076c5ef7d896d1af94f40bce7fa1dd34e49fb5f052a094ddc19a`;
- probe report SHA-256:
  `a22749659d24719f55d321dc57bef318e4cb445b9443a48b80c857bee695d05d`.

This is causal announcement evidence for the new schedule, but positions that were already open
before the update require the previous schedule to remain applicable to that cohort.

### 2. ONDO/PENDLE/RNDR/SAGA/WIF/W update

Article code:
`2efd086c96a7435fb89b3392d5eb6df9`

- published: `2024-04-23T06:07:29.477000Z`;
- effective: `2024-04-23T06:00:00.000000Z`;
- timing: `PUBLISHED_AFTER_EFFECTIVE`;
- existing positions opened before the update: **not affected**;
- source SHA-256:
  `c2ab3ed3042d52233f2fa5968241c63a939b396082e66cd619edc8f6cec732fe`;
- body SHA-256:
  `8560c087b216861b8238cc550e328c9dccc46c2b48e006802f80abd21f115d8c`;
- probe report SHA-256:
  `11af3df822e8c6b4fa6b617a31db84cc6ed85256a86dd55124f9304db0055b31`.

This source is useful retrospective evidence for the historical schedule, but it is **not** proof
that the new schedule was causally known before the effective boundary.

### 3. ASTR/DASH/IOTX/KAVA/KSM update

Article code:
`f9e6ea2d58ce4de5bf9ecadea5170526`

- published: `2024-06-14T03:00:09.819000Z`;
- effective: `2024-06-18T06:50:00.000000Z`;
- timing: `ANNOUNCED_BEFORE_EFFECTIVE`;
- existing positions opened before the update: **affected**;
- source SHA-256:
  `8c73af5fec6272322cdcfd12c6a0fd1772ff6f473d68007df6bfe36266668c05`;
- body SHA-256:
  `6dce58ed361df7e662ffa0bb20e0f753aca2fa6c5ec441504e3b25b6e8607905`;
- probe report SHA-256:
  `2b809598c051204e5575467a44903792fa797506e74c4188fa934f75199ea609`.

Unlike the first two sources, this announcement explicitly states that positions opened before
the update are affected. M11W therefore records cohort policy per revision instead of assuming
one universal rule.

## Compiled evidence

The exact compiled report is committed at:

`docs/data/11w-historical-liquidation-evidence.json`

Git blob SHA:
`ae118a1042cfe888d5119e1c3e176ae9edabd9eb`

File SHA-256:
`85f37fc75f3b489844acdffa91d41625333ffdcce53a6f92daa8ec4899dab6ae`

Internal evidence hash:
`304cdc5a9d65a3ad86be4001babd0ad166b2469431b95e3d8cd095c99768e5f2`

M11W Historical Liquidation Evidence workflow:
- Actions `35651999817`, run #2 — **SUCCESS**;
- artifact ZIP digest:
  `48cbd9c9c907a8db8411b4af5700744d2010f0cad6ae2672dfefeae8346da2a5`.

The compiled result contains:
- source count: **3**;
- USD-M symbols: **13**;
- causally announced changes: **2**;
- retrospective changes: **1**;
- position-cohort policy observed: **true**;
- emitted full ContractRules rows: **0**.

Symbols:
ASTRUSDT, BTCUSDT, DASHUSDT, ETHUSDT, IOTXUSDT, KAVAUSDT, KSMUSDT, ONDOUSDT, PENDLEUSDT, RNDRUSDT, SAGAUSDT, WIFUSDT, WUSDT.

For each selected symbol/revision the evidence preserves:
- previous and new notional boundaries;
- maximum leverage per band;
- maintenance-margin rate per band;
- source publication/availability/effective times;
- causal-vs-retrospective timing;
- whether pre-update positions are affected.

## What M11W does not prove

The official announcement tables do **not** provide the maintenance amount/cum/deduction field
needed to promote the existing liquidation equation to exchange-validated exact history.

Therefore the committed report deliberately keeps:

- `maintenance_amounts_complete=false`;
- `maintenance_deductions_complete=false`;
- `exchange_liquidation_value_validation_complete=false`;
- `historical_liquidation_rules_complete=false`;
- `liquidation_validated=false`;
- `contract_rules_emitted=0`;
- `quality=PRELIMINARY`;
- `operational_ready=false`;
- `live_enabled=false`;
- Final Test `LOCKED`.

No deduction/cum value is invented from current Binance data, from a presumed continuity formula,
or from today's leverage brackets.

The existing `isolated_liquidation()` reconstruction therefore remains PRELIMINARY unless a
future rule record has both historical verification and independent liquidation validation.

## Readiness impact

The pre-Final readiness matrix now points `LIQUIDATION_RULES` to the M11W report instead of the
older M11G funding summary.

The capability remains **PARTIAL**, because:
- the three selected announcements do not form a complete 2020-01-01 through 2025-06-30 change
  stream;
- maintenance amount/cum/deduction history is absent;
- exchange liquidation values have not been independently validated;
- one source is retrospective rather than causally pre-announced;
- cohort/grandfathering behavior varies by update.

This is a stronger and more accurate blocker, not a relaxation of the readiness gate.

PAPER remains **NOT READY**. LIVE remains **DISABLED**. No historical performance run is authorized.
