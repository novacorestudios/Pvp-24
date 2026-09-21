# M11U — Funding settlement-price and schedule evidence audit

## Scope

M11U is a data/provenance milestone only. It does not modify PVB-24 Alpha, signal thresholds,
risk fractions, sizing, leverage, entry/exit logic, execution behavior, the frozen baseline
configuration, or Final Test governance.

The implementation delta from M11T documentation checkpoint
`1e6b0091d41640da0c5d3c9bbe66980f8f59b08a` through code checkpoint
`6450091cb26ef80365740690a64be2ae83b3ea37` is limited to:

- `src/pvb24/data/settlement_audit.py`
- `src/pvb24/data/funding_schedule.py`
- `scripts/audit_funding_schedule.py`
- `tests/test_settlement_audit.py`
- `tests/test_funding_schedule.py`

No strategy, risk, execution, baseline-config, or frozen Alpha file changed.

## Code verification

Code checkpoint: `6450091cb26ef80365740690a64be2ae83b3ea37`.

PVB-24 CI Actions **35640860553 — SUCCESS**:
- Ruff format: passed.
- Ruff lint: passed.
- pytest: **638 passed**.
- provenance verification: passed.
- reference smoke: passed.
- Freqtrade smoke/parity/framework parity: passed.

## Settlement Mark conclusion

The retained M11G source qualification remains authoritative for the pre-Final BTCUSDT funding
sample:

- funding-history rows: **6,117**;
- source-associated settlement Marks present: **1,826**;
- source-associated settlement Marks missing: **4,291**;
- first source Mark present: `2023-10-31T08:00:00.000000Z`;
- last missing source Mark: `2023-10-31T00:00:00.001000Z`;
- source Mark is complete for the selected months from November 2023 onward.

M11U hardens the existing settlement diagnostic so both the Mark 1m **current-minute open** and
the **previous-minute close** can be compared against known source-associated settlement Marks.
Both remain diagnostics only. Neither OHLC field is promoted into a settlement price.

The reason is structural: a Mark-price OHLC bar does not identify the exact point observation used
by the venue for funding settlement. Equality in selected samples cannot prove association, while
known disagreements prove that unconditional substitution is unsafe.

Therefore:
- no missing settlement Mark is filled;
- no nearest-time join is allowed;
- no timestamp rounding is allowed;
- no interpolation is allowed;
- LAST is not substituted for Mark;
- `archive_derived_settlement_prices=0` remains the required behavior.

The **4,291** missing source-associated settlement Marks remain an explicit blocker for exact
historical funding cashflow wherever a replayed position crosses those settlements.

## Retained source bundle

The audit used the original retained recovery bundle:

- file: `PVB24-source-evidence-11G.zip`;
- ZIP SHA-256:
  `85206d50a6148bbbafb285c69eece7fa1a1c8ebd592cb485bdb5448286f7baeb`;
- embedded manifest content hash:
  `2b5bfb58457426104602f3e985a638b326abb4b98dba0fda068da6bd8f4ba089`;
- retained files listed by the manifest: **508**;
- byte/hash/size verification failures during M11U reconsumption: **0**.

The selected M11G summary is:
`data/funding-11g/summaries/c6b722671ce87fe68afd9ab3b261e9e7616cfb06ffe0e17114ce284d86f90920.json`

Its SHA-256 is therefore:
`c6b722671ce87fe68afd9ab3b261e9e7616cfb06ffe0e17114ce284d86f90920`.

Selected data identity:
`7cede73083b59738ce753df2efbac6fd6ffed1e3fad03d9613eece00197a94d4`.

No revised remote funding data was silently substituted for these retained bytes.

## Funding schedule audit

The new `PVB24_FUNDING_SCHEDULE_AUDIT_V1` path revalidates the pinned funding selection and
then examines the exact elapsed time between consecutive official archive settlement rows.

It intentionally does **not** emit `FundingCoverage`. An ex-post list of settlements can prove
what settlements were later observed in the retained source, but it does not by itself prove that
a historical decision between two settlements causally knew the next settlement boundary.

Actual retained result:

- requested months: **67**;
- revalidated months: **67**;
- time/rate matched months: **66**;
- archive unavailable month: **2019-12**;
- archive settlement rows: **6,024**;
- adjacent archive pairs: **6,023**;
- first retained archive settlement: `2020-01-01T00:00:00.000000Z`;
- last retained archive settlement: `2025-06-30T16:00:00.002000Z`;
- declared interval values in the selected archive rows: **8 hours only**;
- exactly declared elapsed pairs: **2,486**;
- non-exact elapsed pairs: **3,537**;
- minimum elapsed-minus-declared difference: **-45 ms**;
- maximum elapsed-minus-declared difference: **+47 ms**;
- maximum absolute difference: **47 ms**;
- pairs large enough to contain an additional whole declared interval: **0**;
- timestamp rounding applied: **false**;
- actual interval index hash:
  `37a8169130caf79a09a25e84071385acacc42efd77a3ef72980c8bab9b25c120`.

This corroborates a continuous **ex-post** settlement-event index across the available official
archive months. It does not convert the observed eight-hour pattern into a causal historical
calendar and does not assume that future periods must also be eight hours.

## Committed result

Report:
`docs/data/11u-funding-schedule-audit.json`

Report document SHA-256:
`327861b288769e17854aff80f10ce641124de2cbf074cab21999f8b63e855541`

Internal audit hash:
`e774d7d89ff81042cb89ad338c3816122b34d25fdcbafb246c5a528bcd68cc9c`.

The result deliberately remains:

- `source_time_rate_comparison_complete=false` because the selected December 2019 archive is
  unavailable;
- `causal_next_settlement_time_verified=false`;
- `funding_schedule_complete=false`;
- `funding_coverage_attestation_emitted=false`;
- `funding_reserve_coverage_qualified=false`;
- `operational_ready=false`;
- `live_enabled=false`;
- Final Test `LOCKED`.

## What M11U proves and does not prove

M11U proves that the retained selected archive settlement rows form a tightly spaced ex-post event
index without evidence of a missing whole declared interval in the acquired archive months. It also
proves that OHLC-derived Mark values remain unqualified as exact settlement prices.

M11U does **not** prove:
- the venue's complete historical next-settlement schedule as known at each decision time;
- exact settlement Marks for the 4,291 missing source rows;
- a complete 30-day causal `FundingCoverage` watermark;
- historical universe/rule completeness;
- historical liquidation tiers;
- operational PAPER readiness.

The existing replay funding-boundary code can prove strategy-owned quantity at an individually
evidenced settlement. That does not cure missing source economics or schedule coverage.

## Next funding blocker

The remaining funding work is now narrower and explicit:

1. find and qualify an exact historical source for the **4,291 missing settlement Marks**, without
   OHLC/LAST substitution; and
2. find and qualify historical evidence that can establish the **next settlement boundary
   causally between settlements**, or keep funding-reserve coverage unqualified.

Until those are solved, funding remains PARTIAL in the historical-readiness gate. No performance
replay should be promoted to VERIFIED on the affected period.
