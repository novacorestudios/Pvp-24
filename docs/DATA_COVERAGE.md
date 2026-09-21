# Official archive sample coverage — Milestone 11A

This is a source-ingestion sample, not a strategy backtest. BTCUSDT January 2024 lies in Validation; no strategy performance was calculated and Final Test remained locked. The choice tests source formats and does not define the historical universe.

| Input | Interval | Rows | Monthly bar grid | SHA-256 |
| --- | --- | ---: | --- | --- |
| fundingRate | Declared per settlement | 93 | Not attested (funding) | `3e0d30870672aa8f0f937881056e3cfd55913ae5c780cd50b33f2763aa0ba58e` |
| klines | 1h | 744 | Complete | `bf673f3d10804a951e8bac56dd2473486f113025971d43ebe5258ec40f9bfeb3` |
| klines | 1m | 44640 | Complete | `21eeac04a76a7a35b10467e5e752fb2f8cff77cdeb57df6b50a23ce8d69bb190` |
| markPriceKlines | 1h | 744 | Complete | `759f86a22dadb455c87a3f90f6a9134c73d24a55a7596f0b96e193b5d45cdb49` |
| markPriceKlines | 1m | 44640 | Complete | `1607b1522928d2a698592019fef7c3fcc9bee2cd01674c72a27e7fc028fd66ca` |

Dataset hash: `985453a92d0283cd4fd6fc60b55296bfe65110b7c8f07baa99ffda3d280bb0a6`.
Report hash (excluding the hash field itself): `34a41240a7745d820b9e5f8b7afc7a348bada0fe77d59b64385bc9106f432526`.

All five objects passed official named SHA-256 verification and complete strict CSV decoding. The four candle grids have no missing intervals in this one month. This does not establish completeness outside the sample.

The 93 funding rows contain 28 differences of 1–3 milliseconds (signed) between actual consecutive settlement timestamps and the declared interval. Original timestamps are retained; funding_schedule_complete=false. Funding interval reconstruction, settlement Mark prices and historical publication timing still require source evidence.

| Required capability | Status |
| --- | --- |
| Full Development/Validation coverage | Not acquired |
| Historical listings/delistings/renames/classifications | Not reconstructed |
| Historical trading filters and margin tiers | Not acquired |
| Continuous causal funding coverage | Unresolved |
| Funding settlement Mark | Acquired for the 93-row January 2024 sample only (11E) |
| Actual publication/receipt times and prior revisions | Unknown; +2s availability model only |
| Sequence-consistent executable quotes/L2 | Not acquired |
| Final Test | Locked; no archive access |
| Performance / operational PAPER / LIVE | Not evaluated / not ready / disabled |

The committed manifest records the acquisition base commit and worktree_dirty=true, with exact decoder/acquirer file hashes. Reproduce using REPRODUCE.md; a changed official object must become a separately recorded revision, never an automatic replacement of this dataset.

## Causal normalization (11B)

The pinned sample was reread through ArchiveDataset at 2024-02-01 00:00:02 UTC: 744 LAST hours, 744 Mark hours and 31 complete daily LAST observations. No interval was filled synthetically. The daily volume source is the sum of 24 available LAST hourly observations; Mark volume is excluded. Derived identity and availability are tied to the exact constituent rows. See data/11b-normalization-summary.json. This supplies only volume inputs for a future universe reconstruction, not evidence that a symbol was historically eligible.

## Source inventory (11C)

Complete enumeration observed 8 monthly source kinds, 9 daily kinds and 1018 monthly kline symbol directories. The four original XML pages are retained. These are source-discovery names, not 1018 historically eligible contracts. No archive content or Final-period market values were downloaded by the inventory. Historical metadata/rules remain unacquired; neither enumerated root exposes those datasets. The discovery of bookTicker/bookDepth directories does not yet qualify order-book coverage.

## Lifecycle evidence review (11D)

Two official pre-Final notices covering five symbols demonstrate distinct publication, trading-cutoff and scheduled-settlement times. Their factual annotations are retained in data/11d-lifecycle-source-review.json. They are not replay inputs: displayed publication timezone and original revision availability remain unqualified. The core now handles explicitly sourced delisting observations without relying on the next daily universe refresh. This integration does not establish historical security-master completeness or prove actual automatic-settlement outcomes.

## Funding source comparison (11E)

The official historical funding endpoint returned 93 Regular BTCUSDT January 2024 records, all with settlement Mark prices. All 93 match the archive exactly on timestamp and rate; no rounding, missing rows or rate mismatches in this sample comparison. Continuous interval qualification and historical availability remain unresolved, and funding_schedule_complete remains false. Raw API evidence and complete diagnostics are committed. No position eligibility or cashflow is inferred.


## 11F — Partial metadata qualification

Three reviewed articles provide five delisting facts (BLUEBIRDUSDT, FOOTBALLUSDT, LOOMUSDT, ORBSUSDT, XEMUSDT) and twelve tick changes effective 2024-03-19 06:30 UTC. Exact source publication times are 2024-03-19 05:05:02.006 UTC, 2024-11-29 04:00:01.809 UTC and 2024-03-18 09:55:15.279 UTC respectively. The twenty-four-hour publication display is no longer used to infer timezone or truncate milliseconds.

The machine-readable 17-row report data/11f-announcement-coverage.json enumerates symbol, dates, source, raw hash and partial facts; it explicitly records missing full security records, full rules and actual settlement fills. Coverage start/end remain null, not an invented continuous range. Two USDC-quoted tick rows are retained as observed data, not admitted to the USDT universe. Known tick-before values do not prove all older rule periods. Delisting cutoffs do not replace PVB-24's immediate announcement-based entry block. All inputs remain PRELIMINARY; three selected articles are not a complete historical metadata catalog.


## 11G — Full pre-Final BTCUSDT Funding source audit

The 67 requested months are individually recorded in data/11g-funding-source-coverage.json: December 2019 warmup plus January 2020–June 2025. There are 66 exact time/rate matches comprising 6024 archived records, against 6117 REST records in all 67 months. The December 2019 archive checksum is unavailable (HTTP 404); its REST history has 93 records. No period was silently removed. This is explicit single-symbol source qualification, not historical universe coverage.

The field-level summary data/11g-funding-qualification.json records 1826 available and 4291 missing settlement Mark prices. Complete monthly Mark coverage begins November 2023; two earlier marks exist on October 31 after the 00:00:00.001 record lacking a mark. No candle price or zero replaces these missing settlement observations.

3503 within-month source interval discrepancies remain visible. The audit compares exact timestamps/rates without reconstructing a funding schedule from the last row or smoothing nominal/actual timestamp differences. Cross-month interval semantics and funding eligibility remain unqualified; source agreement alone cannot enable the reserve/ledger or VERIFIED evaluation. Current metadata provider documentation and an unauthenticated HTTP 401 probe are recorded separately in data/11g-metadata-source-review.json; no complete alternate security/rule history was obtained.
