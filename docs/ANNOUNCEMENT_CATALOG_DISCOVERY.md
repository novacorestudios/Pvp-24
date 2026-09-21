# Official announcement catalog discovery — Milestone 11O

Milestone 11O adds a bounded source-discovery path for the two official Binance Support
announcement categories that are directly relevant to historical security/lifecycle research:

- catalog 48 — New Cryptocurrency Listing;
- catalog 161 — Delisting.

The source is Binance's public CMS article-list endpoint. This milestone does **not** promote
catalog membership, article titles, archive-directory presence or today's catalog ordering into
historical trading eligibility. It only creates a content-addressed candidate inventory for
later body acquisition and independent semantic review.

The adapter validates the requested catalog identity, exact integer source clocks, article IDs,
legacy 12-digit and modern 32-hex article codes, newest-first ordering, page bounds, duplicate
codes and stable observed catalog total within one acquisition slice. Every raw page is retained
by SHA-256 and revalidated before reuse.

## Final-Test isolation

Current announcement pagination can contain newer holdout rows before the Development/Validation
history. The research engine therefore never auto-discovers a starting page. A caller must supply
an explicitly reviewed `start_page`, and every fetched row must already be below the requested
pre-Final upper boundary. A mixed page containing a Final-period row fails closed instead of
filtering that row away and continuing.

This is intentionally conservative. It prevents an automated source crawl from silently reading
through the locked Final Test simply to reach older announcements.

## What completion means

`catalog_slice_complete=true` means only that the requested bounded catalog slice reached its
lower time boundary without source/pagination ambiguity. It does **not** mean:

- the historical universe is complete;
- a security master is complete;
- every futures listing/delisting article has been semantically qualified;
- the current article body equals the original historical revision;
- historical receipt latency is known;
- performance, PAPER or LIVE is ready.

The next step after a clean catalog inventory is to acquire the retained bodies for relevant
pre-Final candidates, validate listing/delisting facts through the existing announcement decoder,
and reconcile those facts with causal archive activity before any
`HISTORICAL_UNIVERSE` attestation can be considered.

## Reviewed candidate inventory and source replay (M11P)

Use `scripts/build_announcement_inventory.py` with explicit retained catalog report hashes;
report dictionaries alone are not a provenance boundary. Reconsumption now reconstructs the
exact article selection from the ordered source page chain, checks receipt/pagination/terminal
evidence and rejects changed rows even if a report's article hash is recomputed. Acquisition
validates pages before retaining raw bytes, including every row's pre-Final upper boundary.
Short pages inconsistent with the declared total cannot silently establish completion.

Inventory output links every candidate to a report pin, counts unmatched titles and explicitly
keeps title-filter recall and historical publication timing unverified. See
[POST_M11O_REVIEW.md](POST_M11O_REVIEW.md) for review findings, safe offline use and the exact
remaining source acquisition prerequisite. No production candidate inventory or historical
universe completion is claimed by the synthetic tests.
