# Data provenance

Milestone 11A acquired five official BTCUSDT January 2024 monthly archives: LAST and Mark candles at 1m/1h, and raw funding settlements. No performance run executed; Final Test remains locked. See DATA_COVERAGE.md and data/11a-source-manifest.json for the exact sample, revisions, hashes and unresolved coverage.
Required coverage: Last OHLCV 1h/1m, Mark, funding settlement history, historical contract rules, security master with classifications/listings/delistings, and sequence-consistent Quotes/L2 for VERIFIED execution. Missing funding is never zero. Current contract metadata is not historical proof.

## Implemented contracts

Causal reads select the latest revision available by decision time, never a later revision. Conflicting observations at the same availability time fail closed. Universe construction requires a daily security master and the prior 30 completed UTC days. Incomplete historical metadata explicitly yields PRELIMINARY quality. Unknown classification is ineligible; no current Top-20 feed is used for history. Synthetic tests carry synthetic-fixture provenance; VERIFIED in a fixture is a test input and is not a claim about real market data.

## Official archive acquisition (11A)

Sources reviewed on 2026-09-20:

- https://github.com/binance/binance-public-data — official archive layout, futures kline schema, SHA-256 sidecars, and possible later archive corrections.
- https://data.binance.vision/ — public monthly USD-M source objects; each exact URL is recorded in the manifest.
- https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data — current API semantics for klines, Mark klines, funding history and exchange information. Current exchange information is not evidence of historical rules or historical universe membership.

The downloader restricts requests to explicit monthly USD-M archives and validates the entire batch against the locked Final boundary before any network request. It verifies the filename-bound official SHA-256 sidecar, retains immutable content-addressed bytes and attempt records, and records failures independently. A missing archive is never converted into zero activity. Decoder/acquirer hashes identify the implementation used while the acquisition report honestly records its base commit and dirty worktree.

Decoding checks the sole CSV member, schema, exact decimal values, UTC bar boundaries, strict timestamp ordering and source volumes. LAST and Mark remain distinct. Availability is explicitly modelled at interval end plus two seconds; actual historical receipt/publication time is unknown. The sample is PRELIMINARY, even when archive checksums and monthly candle grids are complete.

Funding rows preserve original calc_time and separately declared interval hours. The sample contains millisecond discrepancies between consecutive actual timestamps and declared durations. No rounding, inferred contiguous schedule, fabricated Mark settlement price, or automatic FundingCoverage attestation is applied. Raw funding evidence cannot yet be passed to the causal funding-reserve or cashflow path.

Reconsumption rechecks attempt and object hashes, decoder identity and decoded coverage. It never silently selects a newer archive revision. Raw objects are reproducible ignored research inputs; the committed source manifest preserves their identities and measured coverage, not a claim that a fresh download will always return the same revision.
