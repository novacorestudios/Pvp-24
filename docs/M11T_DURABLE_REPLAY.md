# M11T durable replay gate

This gate reuses the exact M11T raw evidence preserved by F6. It does not fetch
current announcement revisions and does not substitute replacement source data.

The replay performs three checks in order:

1. **Qualification diagnostic replay** — all 148 retained announcement objects are
   re-qualified against the pinned candidate inventory with the current parser.
   The original report remains immutable and remains the downstream input.
2. **Lifecycle recovery replay** — the retained qualification sources are processed
   by the bounded recovery path currently used by M11X.
3. **Historical metadata compilation** — the pinned qualification and lifecycle
   reconciliation reports are compiled with the committed tick evidence.

The audited replay found 60 qualification-semantic differences versus the original
M11T qualification run. Fifty-six are LISTING rows that were
`SEMANTIC_UNQUALIFIED` in M11T and are parseable as `QUALIFIED_PRELIMINARY` by
the current parser. Four remain `SEMANTIC_UNQUALIFIED` and only their explicit
failure reason changed. These observations are diagnostic only: they are not
silently substituted into M11V or the Security Master.

The complete per-source diff is emitted in
`11t-durable-replay-comparison.json`. Its exact change set is pinned by
`change_hash=041cef54af1f87f786e96851e692f57853ca9f2b9edbaaa6618f6058884dbbf8`.
The current semantic replay hash is
`7837b810a5955681ca03404561740c8e890aade4f88c14f97ba1061f91e8134a`.

Despite those diagnostic qualification differences, the bounded M11X recovery is
unchanged:

- output SHA-256:
  `aedcd648151c26968268c1580b7c6bf10284a1d1774c86bc21074f7fe697943d`
- recovery hash:
  `24bcdc421db1d6f32122ed293720d43ae824db94a8f8a4c74a2d6f8d310a9d3c`
- 32 recovered articles / 48 facts / 45 symbols
- 24 listing facts / 24 delisting facts / 88 remaining semantic failures

Historical metadata compilation is also byte-identical:

- output SHA-256:
  `8130ae8d57cb60747daaef379a1713a990937d499a86360c920d0584a7e20252`
- evidence hash:
  `4794c5f0fb40ef343523d56744c6e7a9e9fa7b24fcdd22879df7f7af078bc26d`
- 15 listing candidates / 7 unresolved listings / 11 delisting events /
  10 tick-field events
- `historical_universe_complete=false`

The baseline is committed at
`docs/data/11t-durable-replay-baseline.json`. Future changes to source bytes,
qualification semantics, recovery output or compilation output fail the replay
workflow unless independently reviewed and deliberately re-baselined.

The gate does not modify Strategy/Alpha, thresholds, sizing, risk, leverage, entry
or exit logic. Final Test remains LOCKED and LIVE remains disabled.
