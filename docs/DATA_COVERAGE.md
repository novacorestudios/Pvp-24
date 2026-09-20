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
| Continuous causal funding coverage and settlement Mark | Unresolved |
| Actual publication/receipt times and prior revisions | Unknown; +2s availability model only |
| Sequence-consistent executable quotes/L2 | Not acquired |
| Final Test | Locked; no archive access |
| Performance / operational PAPER / LIVE | Not evaluated / not ready / disabled |

The committed manifest records the acquisition base commit and worktree_dirty=true, with exact decoder/acquirer file hashes. Reproduce using REPRODUCE.md; a changed official object must become a separately recorded revision, never an automatic replacement of this dataset.

## Causal normalization (11B)

The pinned sample was reread through ArchiveDataset at 2024-02-01 00:00:02 UTC: 744 LAST hours, 744 Mark hours and 31 complete daily LAST observations. No interval was filled synthetically. The daily volume source is the sum of 24 available LAST hourly observations; Mark volume is excluded. Derived identity and availability are tied to the exact constituent rows. See data/11b-normalization-summary.json. This supplies only volume inputs for a future universe reconstruction, not evidence that a symbol was historically eligible.
