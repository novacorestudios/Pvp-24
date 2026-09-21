# Reviewed pre-Final announcement anchors

M11Q establishes a fail-closed path for deriving a safe CMS start page from independently reviewed
official Binance announcement evidence.

The current official Support catalog UI was reviewed on 2026-09-21. It exposed 227 UI pages for
New Cryptocurrency Listing (catalog 48) and 44 UI pages for Delisting (catalog 161). Those counts
are used only to bound an **old-page search hint**; they are not treated as a CMS total, a
historical-universe count, or a completeness attestation.

Reviewed pre-Final detail anchors:

- Catalog 48:
  `fb8600ebb2ae4e80a0db1945e683993c`, published `2025-06-30T07:00:00Z`.
- Catalog 161:
  `173b2a63c03141009029407ecfebd14a`, published `2025-06-26T07:00:00Z`.

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
- https://www.binance.com/en/support/announcement/detail/fb8600ebb2ae4e80a0db1945e683993c
- https://www.binance.com/en/support/announcement/detail/173b2a63c03141009029407ecfebd14a
