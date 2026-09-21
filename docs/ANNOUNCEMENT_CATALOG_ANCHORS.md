# Reviewed pre-Final announcement anchors

This checkpoint establishes a fail-closed way to derive a **safe starting page** for the official
Binance announcement catalogs without crawling from the newest catalog rows through the locked
Final Test period.

The reviewed public anchors are intentionally before the Final Test boundary
(`2025-07-01T00:00:00Z`):

- Catalog 48 (New Cryptocurrency Listing / new trading-pair announcements):
  `fb8600ebb2ae4e80a0db1945e683993c`, published `2025-06-30T07:00:00Z`,
  https://www.binance.com/en/support/announcement/detail/fb8600ebb2ae4e80a0db1945e683993c
- Catalog 161 (Delisting):
  `173b2a63c03141009029407ecfebd14a`, published `2025-06-26T07:00:00Z`,
  https://www.binance.com/en/support/announcement/detail/173b2a63c03141009029407ecfebd14a

These detail pages are only **review anchors**. Their existence does not by itself attest catalog
membership, historical receipt latency, lifecycle facts, complete universe coverage, or
`available_at`.

`review_announcement_catalog_anchor.py` asks the official CMS for an empty out-of-range page to
obtain the exact current catalog total, then walks **from the oldest singleton row toward the
reviewed anchor**. It stops on the exact article code and exact release clock. It does not
intentionally request rows newer than the anchor to discover its position. From that ordinal it
selects the first normal-size catalog page that cannot contain an ordinal newer than the anchor,
and revalidates that page before pinning its raw bytes and report by SHA-256.

All output remains `PRELIMINARY`. Final Test access stays `LOCKED`; historical universe,
security master, lifecycle completeness, performance readiness, PAPER readiness, and LIVE remain
false until their independent evidence gates pass.

If the anchor is absent, its release clock differs, the catalog total changes, ordering drifts, or
the scan reaches Final before the anchor, the review fails closed and no start page is promoted.
