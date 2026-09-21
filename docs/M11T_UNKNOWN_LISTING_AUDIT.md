# M11T — UNKNOWN listing boundary audit

## Scope

This checkpoint investigates only the seven listing reconciliations that remained `UNKNOWN` after
M11S. It does not modify PVB-24 Alpha, thresholds, risk rules, sizing, leverage, entry/exit logic,
execution logic, baseline configuration, or the frozen Final Test boundary.

The implementation delta from
`29bf6fee787cf8912d552ee81eebfba20fefe9b5` through
`c7a1fe4d3b51ad0ac0e0f94ae76da9c647029ddb` is limited to announcement/lifecycle
data modules, the two evidence scripts, and four regression-test files. No strategy, risk,
execution, or frozen Alpha/configuration file changed.

## Verification

Code checkpoint: `c7a1fe4d3b51ad0ac0e0f94ae76da9c647029ddb`.

PVB-24 CI Actions **35637293211 — SUCCESS**:
- Ruff format check: passed.
- Ruff lint: passed.
- pytest: **633 passed**.
- provenance: passed.
- reference smoke: passed.
- Freqtrade smoke/parity/framework parity: passed.

Source-evidence workflow Actions **35636682664 — SUCCESS** on
`c51a89b15030a5d5996a6fc3877969bcf112d757`. The later commits through the code
checkpoint are test-formatting-only; production lifecycle semantics are unchanged.

## Listing revision discovery correction

Catalog 48 already contained the official article
`fdbcf19f900c4c45b1e836f5c8da2550`, titled
“DOT USDT-Margined Perpetual Contract Listing Delayed to 2020/08/22”, but the prior title
discovery rules did not select listing-delay/revision titles.

The discovery layer now recognizes listing delay/postponement/reschedule candidates. The strict
listing decoder recognizes an explicit old schedule and replacement schedule without inventing
missing leverage or other metadata.

A listing postponement is not allowed to rewrite history retroactively:
- if the revision is available on or before the prior scheduled event, it may causally supersede
  that future schedule;
- if the revision becomes available only after the prior scheduled event, the prior event remains
  in the audit trail and the replacement is recorded as a `late_revision`.

No arbitrary minute tolerance was introduced.

## DOT causal chain

Original official listing article:
- code: `ff90e1242b2546a1a46dd51d4b004927`;
- published: `2020-08-19T07:00:05.366000Z`;
- preliminary available-at: `2020-08-19T07:00:07.366000Z`;
- scheduled launch: `2020-08-20T07:00:00Z`;
- announced maximum leverage: 50x.

Official delay article:
- code: `fdbcf19f900c4c45b1e836f5c8da2550`;
- published: `2020-08-20T07:45:59.089000Z`;
- preliminary available-at: `2020-08-20T07:46:01.089000Z`;
- explicitly references the previous launch `2020-08-20T07:00:00Z`;
- replacement launch: `2020-08-22T07:00:00Z`.

Because the delay article became available after the original 07:00 event, M11T does **not**
pretend that a replay at 07:00 knew about the later revision. The original 20-Aug boundary stays
`UNKNOWN`. The replacement 22-Aug boundary is separately reconciled and is
`CONSISTENT_EVENT_BOUNDARY_ONLY`: the official daily LAST 1m archive begins exactly at
`2020-08-22T07:00:00Z`.

## Seven UNKNOWN records after investigation

All seven remain explicit UNKNOWN records; investigation does not manufacture certainty.

| Symbol | Announced event | First active LAST 1m / archive state | Audit conclusion |
| --- | --- | --- | --- |
| WAVESUSDT | 2020-08-12 07:00 UTC | first active 07:01; prior-day object unavailable | UNKNOWN; a one-minute delay is not promoted into a tolerance rule |
| SNXUSDT | 2020-08-14 07:00 UTC | first active 07:02; prior-day object unavailable | UNKNOWN; no qualifying retained revision proves a different launch |
| DOTUSDT | 2020-08-20 07:00 UTC | event-day and prior-day objects unavailable | UNKNOWN for the original schedule; a later official revision creates a separate 22-Aug boundary |
| STORJUSDT | 2020-09-16 07:00 UTC | first active 07:03; prior-day object unavailable | UNKNOWN; delayed first trading activity alone does not prove a revised launch |
| BLZUSDT | 2020-09-17 07:00 UTC | first active 07:02; prior-day object unavailable | UNKNOWN; no arbitrary timing tolerance |
| NEARUSDT | 2020-10-15 07:00 UTC | first active 08:00; prior-day object unavailable | UNKNOWN; the one-hour discrepancy requires retained historical revision evidence before promotion |
| MATICUSDT | 2020-10-22 07:00 UTC | first active 07:01; prior-day object unavailable | UNKNOWN; a one-minute delay is not treated as proof of a revised schedule |

A missing archive object never proves inactivity. Likewise, a first trade after the announced
listing time is not by itself a contradiction: there can be a period with no trades after a
contract becomes available. Therefore none of these records is promoted to a verified lifecycle
boundary without stronger retained historical evidence.

## M11T real-data result

Pinned catalog rows reviewed: **680**.

Candidate inventory:
- candidates: **148**;
- inventory report SHA-256:
  `07ba9ba9e59ab2823d545d687bb157744d855ce971361b6da13b3f2274430cf1`;
- inventory artifact digest:
  `sha256:69018e311d3aafed8985524f5d09e8f08e27551e5dfa50d8cc1c25831c478e43`.

Qualification V3:
- `QUALIFIED_PRELIMINARY`: **28**;
- `SEMANTIC_UNQUALIFIED`: **120**;
- source fetch complete: true;
- qualification report SHA-256:
  `ed5539a48c6fca0fca16823bfd4dfd60ad3048c57716635adbb5d04d4b5ddd3a`;
- qualification artifact digest:
  `sha256:95095899140c1fdfa38db7f171fe7ba5ad4c1d655fe8915d696d42f0c55b7647`.

Lifecycle reconciliation V3:
- qualified lifecycle facts: **35**;
- causally effective records retained for reconciliation: **33**;
- causally superseded schedules: **2**;
- late listing revisions retained for audit: **1**;
- official daily LAST 1m probes: **66**;
- reconciliations: **33**;
- `CONSISTENT_EVENT_BOUNDARY_ONLY`: **26**;
- `UNKNOWN`: **7**;
- `CONTRADICTED_BY_ARCHIVE_ACTIVITY`: **0**;
- source failures: **0**;
- reconciliation report SHA-256:
  `2c935625dffef3a949b7b30c4dfb55ca75b6b78c70771958d710c6925a0253bd`;
- lifecycle artifact digest:
  `sha256:4d8cbb1a7e69acc9ae0ba2fd9e34ae22add956643b847125d853ac9869343021`.

## What this does not prove

M11T does not set `historical_lifecycle_verified=true`. The pinned announcement catalogs are still
not proven to be a complete historical security master, the seven original UNKNOWN boundaries
remain unresolved, and current/retrospective metadata is not substituted for a historical snapshot.

Final Test remains LOCKED. `operational_ready=false`. PAPER is NOT READY. LIVE is DISABLED.

## Next blocker

The next independent blocker is funding evidence, including the previously identified **4,291
missing BTCUSDT funding-settlement Marks**, plus historical funding schedule/reserve/eligibility.
Missing funding or Mark data must not be converted to zero.
