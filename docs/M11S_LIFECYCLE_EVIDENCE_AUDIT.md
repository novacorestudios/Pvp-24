# M11S lifecycle evidence recovery audit

## Scope

This checkpoint audits and repairs only historical announcement/lifecycle evidence added after the
M11P baseline `ca5acbfb6d80d721e58c18462f9d6c02b23f9f5d`. It does not modify PVB-24 Alpha,
thresholds, risk rules, entry/exit logic, leverage, sizing, or the frozen Final Test boundary.

A repository comparison through `87e2c0ad0dec05c543d52f3aa5f041713cb911ce` shows post-M11P changes only in data/provenance
modules, acquisition/reconciliation scripts, tests, documentation and CI workflow files.

## Root cause corrected

The daily LAST 1m archive decoder stored the previous bar's interval end and rejected the next bar
when `start <= previous_end`. For normal contiguous half-open intervals the next start is exactly
the previous end, so valid consecutive 1m bars were incorrectly classified as failed source data.

The condition now rejects only `start < previous_end`. Equality is valid continuity; a strictly
later start records an explicit gap. A direct regression test covers two contiguous minute bars.

CI workflow paths were also corrected so changes to `daily_activity.py` or
`reconcile_lifecycle_activity.py` automatically rerun the catalog/lifecycle evidence workflow.

## Verification

Current code checkpoint: `87e2c0ad0dec05c543d52f3aa5f041713cb911ce`.

PVB-24 CI Actions **35631163230 — SUCCESS**:
- Ruff format check: passed.
- Ruff lint: passed.
- pytest: **624 passed**.
- provenance: passed.
- reference smoke: passed.
- Freqtrade smoke/parity/framework parity: passed.

Source-evidence workflow Actions **35630904789 — SUCCESS** on
`ba6eb53bd949139def0eabb83d5159b6c7a1d917`. The later current-HEAD change only corrects the
native-datetime assertion in the new regression test; lifecycle/data source logic is unchanged.

## Announcement qualification evidence

- Candidate catalog rows reviewed: 680.
- Title-selected candidates: 146.
- Official detail fetch failures: 0.
- `QUALIFIED_PRELIMINARY`: 25.
- `SEMANTIC_UNQUALIFIED`: 121.
- Qualification report SHA-256:
  `d95403c325d70555025b02b75b55b8034e84e5b556ae3b1adb6df44a4c800487`.
- Qualification artifact digest:
  `sha256:49e466604ec35716ee79313f9f172a39f05ea13767ceb4a0a57149a8fb7c2eab`.

A semantically qualified body is still PRELIMINARY. It is not proof that the retained CMS body is
the exact historical revision originally visible at publication time, and it does not establish a
complete security master.

## Lifecycle/archive reconciliation evidence

The qualified facts produced 64 checksum-verified official daily USD-M LAST 1m probes and 32
lifecycle reconciliations, with zero source failures:

- `CONSISTENT_EVENT_BOUNDARY_ONLY`: 14.
- `CONTRADICTED_BY_ARCHIVE_ACTIVITY`: 11.
- `UNKNOWN`: 7.

Reconciliation report SHA-256:
`64ecfe8ea042b9cfc078278a4c307bf5db2bb61dcfcad715bb7f38306a939941`.

Lifecycle artifact digest:
`sha256:39a146162c8e5451b61836359bda38865d389b3f7e34ede11a1e01b76303f01d`.

A missing archive object is explicitly UNKNOWN and never proves inactivity. A
`CONSISTENT_EVENT_BOUNDARY_ONLY` result corroborates only the observed archive boundary; it does
not prove full historical lifecycle eligibility. A contradiction is retained as evidence and is
not overridden to fit an announcement.

## Remaining blockers / next action

Investigate the 11 contradicted and 7 unknown reconciliations individually against retained source
bytes and official source semantics. Do not promote unresolved lifecycle facts into a historical
security master.

The previously known blockers remain, including 4,291 missing BTCUSDT funding settlement Marks,
funding schedule/reserve/eligibility, complete historical security/universe/rule snapshots,
historical liquidation tiers, and exchange liquidation validation.

Final Test remains **LOCKED**. `operational_ready=false`. PAPER is **NOT READY**. LIVE remains
**DISABLED**.
