# Reviewed pre-Final announcement anchors

M11Q establishes a fail-closed path for deriving a safe CMS start page from independently reviewed
official Binance announcement evidence.

The current official Support catalog UI was reviewed on 2026-09-21. It exposed 227 UI pages for
New Cryptocurrency Listing (catalog 48) and 44 UI pages for Delisting (catalog 161). Those counts
are used only to bound an **old-page search hint**; they are not treated as a CMS total, a
historical-universe count, or a completeness attestation.

Reviewed pre-Final detail anchors:

- Catalog 48:
  `cd4d635399374a68ace90874ce8b9eb2` ("Binance Will List Conflux Network (CFX)"),
  CMS release clock `2021-03-29T06:54:02.522000Z`. The official detail page independently
  corroborates the article and minute-level publication time.
- Catalog 161:
  `85c046a0853b43c2b791ffc3343ed7f0` ("Notice of Removal of Spot Trading Pairs -
  2025-01-17"), CMS release clock `2025-01-15T07:00:13.729000Z`. The official detail page
  independently corroborates the article and minute-level publication time.

Earlier near-Final anchors (2025-06-30 for catalog 48 and 2025-06-26 for catalog 161) were tested
and deliberately **not** accepted: the walk either encountered a source-order anomaly before the
catalog-48 anchor or reached a page containing Final-period rows before the catalog-161 anchor.
The guard remained fail-closed. No Final row is promoted or used as lifecycle evidence.

These older anchors therefore establish only bounded retained pre-Final source coverage. They do
not close the upper gaps from the accepted anchor to `2025-07-01T00:00:00Z`. Those gaps remain
explicitly incomplete and must be qualified separately before historical-universe completeness.

The reviewer starts from a conservative old CMS page hint (114 for catalog 48, 22 for catalog 161).
An out-of-range HTTP 400 may be backed off only before the first valid page. From the first valid
page it walks toward newer page numbers one page at a time. Every decoded row must remain strictly
before `2025-07-01T00:00:00Z`; a mixed/Final page fails closed and its bytes are not retained.
The exact reviewed article code and release clock must be encountered before source time advances
past the anchor.

All accepted source pages and the resulting report are content-addressed. The result remains
`PRELIMINARY`: title/catalog evidence does not establish lifecycle eligibility,
`available_at`, complete historical universe/security master, performance readiness, PAPER
readiness, or LIVE readiness.

Official source pages:
- https://www.binance.com/en/support/announcement/list/48
- https://www.binance.com/en/support/announcement/list/161
- https://www.binance.com/en/support/announcement/detail/cd4d635399374a68ace90874ce8b9eb2
- https://www.binance.com/en/support/announcement/detail/85c046a0853b43c2b791ffc3343ed7f0

## Replay-bound acquisition path

The production-safe acquisition entrypoint is now
`scripts/acquire_reviewed_announcement_catalog.py`. It never accepts a manually supplied
`start_page`: it first creates the reviewed anchor report, replays every retained source page from
its content-addressed objects, verifies the report SHA-256, and only then derives
`safe_start_page` for the older-page acquisition.

The resulting binding summary deliberately reports
`requested_window_complete=false` and `upper_boundary_coverage_proven=false`. Reaching the lower
boundary from a safe retained anchor proves only that selected older page chain; it does **not**
fill the newer gap between that anchor and 2025-07-01. Those gaps remain blockers for complete
historical lifecycle/universe evidence. Final Test remains LOCKED.
