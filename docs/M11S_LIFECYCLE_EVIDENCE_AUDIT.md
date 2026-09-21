# M11S lifecycle evidence recovery audit

## Scope

This checkpoint repairs only historical announcement/lifecycle evidence after the M11P baseline
`ca5acbfb6d80d721e58c18462f9d6c02b23f9f5d`. PVB-24 Alpha, thresholds, risk rules,
entry/exit logic, leverage, sizing, execution logic, baseline configuration and the frozen Final
Test boundary are unchanged.

The final correction set from `cbe152332656dfb9624b0f2971188c6084d79693` through
`8351633d5f14238642c0e3cbe64a039cc2fad16d` modifies only announcement/lifecycle data modules, scripts and tests.

## Root causes corrected

### 1. Contiguous 1m intervals

The original daily LAST decoder stored the previous interval end and rejected the next bar when
`start <= previous_end`. Normal contiguous half-open 1m intervals have
`next_start == previous_end`; the decoder now rejects only overlap/backwards input
(`start < previous_end`) and records a gap only when `start > previous_end`.

### 2. Archive rows are not automatically trading activity

Binance daily archives can retain 1m rows after a delisting boundary with zero volume and zero
trades. Reconciliation V2 now records explicit active-row statistics and treats only nonzero
volume/trade rows as trading activity. Synthetic zero-activity rows no longer create false
post-settlement contradictions. Activity at the exact announced settlement minute is retained as
boundary evidence and is not treated as activity strictly after settlement.

### 3. Causal delisting postponements

The retained catalog already contained two official OMGUSDT postponement articles, but the V1
extractor rejected them because they do not repeat the original announcement's entry-cutoff
sentence. Qualification V2 recognizes an explicit USDⓈ-M perpetual delisting postponement as a
schedule revision without fabricating an entry cutoff.

Reconciliation applies a postponement only when the revision was available no later than the
currently active scheduled event. The superseded schedule remains in the report audit trail;
nothing is rewritten retroactively. The OMGUSDT chain therefore retains two superseded schedules
and reconciles the final causally effective schedule.

## Verification

Corrected code checkpoint: `8351633d5f14238642c0e3cbe64a039cc2fad16d`.

PVB-24 CI Actions **35633773768 — SUCCESS**:
- Ruff format check: passed.
- Ruff lint: passed.
- pytest: **629 passed**.
- provenance: passed.
- reference smoke: passed.
- Freqtrade smoke/parity/framework parity: passed.

Corrected source-evidence workflow Actions **35633393635 — SUCCESS** on
`9df9dc626eb98258c7d89ae231929bb608355099`. Later commits through the corrected code
checkpoint are formatting/test-lint-only and do not change production lifecycle semantics.

## Announcement qualification V2

- Catalog rows reviewed: 680.
- Title-selected candidates: 146.
- Official detail fetch failures: 0.
- `QUALIFIED_PRELIMINARY`: 27.
- `SEMANTIC_UNQUALIFIED`: 119.
- Qualification report SHA-256:
  `26183381bf2324b38e17ffaff9d6b5bf114c0183d5966c8a9eea1420529b8bd5`.
- Qualification artifact digest:
  `sha256:96df948afa92feb2dd4d7414310f38094531e52d01c45f123c492fdec16d9a45`.

The two additional qualified records are schedule-revision evidence, not new independent
delistings. All qualification remains PRELIMINARY and does not prove that the current retained CMS
body is the exact original historical revision.

## Lifecycle/archive reconciliation V2

The source evidence produced:

- qualified lifecycle facts: 34;
- causally superseded schedules retained for audit: 2;
- effective lifecycle facts: 32;
- checksum-verified daily USD-M LAST 1m probes: 64;
- source failures: 0;
- `CONSISTENT_EVENT_BOUNDARY_ONLY`: 25;
- `UNKNOWN`: 7;
- `CONTRADICTED_BY_ARCHIVE_ACTIVITY`: 0.

Reconciliation report SHA-256:
`9568da9fdc5057c294314a913ea6f0d504aa475902281e4ec2db522cb75f58f5`.

Lifecycle artifact digest:
`sha256:6b99bc0ac8f4ed84c732671f7337510f3c690583907531b923784eeaef035541`.

The seven UNKNOWN records remain unresolved rather than being forced into consistency. Missing
archive objects, or event-day activity that begins after the announced boundary, do not prove
inactivity or prove a lifecycle boundary.

`CONSISTENT_EVENT_BOUNDARY_ONLY` is deliberately narrow corroboration. It does not set
`historical_lifecycle_verified=true`, does not establish listing age or historical eligibility,
and does not complete the historical security master.

## Remaining blockers / next action

Investigate the seven UNKNOWN listing boundaries using retained official evidence only. Do not
promote unresolved lifecycle facts.

The previously known blockers remain, including 4,291 missing BTCUSDT funding settlement Marks,
funding schedule/reserve/eligibility, complete historical security/universe/rule snapshots,
historical liquidation tiers, and exchange liquidation validation.

Final Test remains **LOCKED**. `operational_ready=false`. PAPER is **NOT READY**. LIVE remains
**DISABLED**.
