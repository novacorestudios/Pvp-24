# M11T durable replay gate

This gate reuses the exact M11T raw evidence preserved by F6. It does not fetch
current announcement revisions and does not substitute replacement source data.

The replay performs three checks in order:

1. **Qualification replay** — every retained announcement object is re-qualified
   against the pinned candidate inventory. The original qualification report
   identity, status counts, result hash and review-request hash must still match.
2. **Lifecycle recovery replay** — the retained qualification sources are processed
   by the current bounded recovery code. Output SHA-256, recovery hash and all
   audited counts must match the baseline.
3. **Historical metadata compilation** — the pinned qualification and lifecycle
   reconciliation reports are compiled with the committed tick evidence. Output
   SHA-256, evidence hash and audited counts must match the baseline.

The baseline is committed at
`docs/data/11t-durable-replay-baseline.json`. Any mismatch is emitted in the
comparison report and fails the workflow. This converts the post-F6 replay into a
repeatable regression gate instead of a one-time manual observation.

The gate does not modify Strategy/Alpha, thresholds, sizing, risk, leverage, entry
or exit logic. Final Test remains LOCKED and LIVE remains disabled.
