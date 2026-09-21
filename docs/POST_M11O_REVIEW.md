# Post-M11O manual-change review and M11P inventory boundary

Scope: `eecaab8` (handoff checkpoint), `b7174c7` (candidate inventory), and `11ebe78` (inventory tests), plus their directly used catalog loader/acquirer. No earlier strategy stage was re-audited. The incoming diff changed only HANDOFF, announcement_inventory.py and its tests; no Alpha, thresholds, risk, funding/settlement, readiness implementation, reference or baseline config was modified.

| Root cause | Correction |
| --- | --- |
| One condition failed Ruff formatting; governance stopped before tests. | Formatted it and ran lint, targeted tests and the full suite. |
| ISO/datetime catalog timestamps were passed to an integer-millisecond decoder; all three incoming tests failed. | Use aware ISO/datetime parsing with no rounding; reject naive timestamps and Final windows. Correct the mismatched error-message assertion. |
| A report could recompute its own article hash without proving correspondence to retained pages. | Public inventory construction now requires explicit `CatalogSlice(root, report, sha256)` pins and replays source pages. The report-only transform is private. |
| Catalog reconsumption hashed pages but did not reconstruct rows or prove the page chain. | Rebuild exact articles and in-window selection; validate sequential page numbers/URLs, receipt order, stable total, declared page lengths, lower-boundary/terminal evidence, cross-page ordering, duplicate identities and immutable PRELIMINARY/locked flags. |
| Acquisition wrote raw bytes before checking the Final/upper boundary. | Decode and validate the whole page before retaining bytes. Invalid/mixed Final pages produce an INCOMPLETE failure report without their raw page, rows or page reference. |
| Short/empty responses could be interpreted as completion even when the declared total implied remaining rows. | Require count consistency with the requested page position and total before accepting the page. |

CI recovery checkpoint: `7bed530b7907f8b3a2eeefe35e33924cae6300f5`, Actions **35616597202 SUCCESS**, 581 tests. The subsequent source-boundary checkpoint must pass its own full CI before publication is accepted.

The manually added title filters and deterministic ordering are retained. Titles remain discovery hints: no symbol, listing eligibility, `available_at`, lifecycle event, schedule, settlement price or complete-universe attestation is inferred. Unmatched rows are counted, retained source pages remain addressable, and title-filter recall is explicitly unverified. Catalog release dates are not original body publication/receipt evidence. All inventory outputs stay PRELIMINARY with historical publication verification, operational readiness and LIVE disabled.

New offline entrypoint:

```bash
python scripts/build_announcement_inventory.py \
  --slice SOURCE_ROOT reports/REPORT_SHA256.json REPORT_SHA256 \
  --output artifacts/announcement-inventory
```

Supply a second `--slice` for the other catalog if available; both must use the same pre-Final window. The resulting report is content-addressed and includes report/page hashes, source URLs, receipt timestamps, the filter implementation hash and each candidate's originating report pin. No network request or body acquisition occurs in this command. Changing the catalog decoder intentionally invalidates older decoder pins; never edit an old report's decoder hash merely to force acceptance. Explicitly requalify retained evidence under the new checks.

Source limitation: no acquired production catalog slice or reviewed safe `start_page` is recorded in the current repository evidence. Therefore this checkpoint supplies tested ingestion/qualification code, not an invented historical inventory. Do not guess a page or crawl newer announcements through Final to find one. Next: obtain a reviewed pre-Final catalog starting position (or an independently reviewed retained catalog slice), acquire/requalify and pin it, run the offline inventory, then acquire and semantically qualify candidate article bodies through the existing decoder. A completed selected catalog slice is not proof that all announcements in the entire historical window were discovered.

Existing blockers remain: 4,291 BTCUSDT settlement Marks, incomplete funding schedule/reserve/position eligibility, complete historical security/universe/rule snapshots and liquidation tiers. The M11M performance gate stays blocked. No real market dataset was redownloaded, no performance run occurred, and no external orders were sent during this review.
