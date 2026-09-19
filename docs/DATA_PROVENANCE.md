# Data provenance

No market data acquired; no performance run executed; Final Test remains locked.
Required coverage: Last OHLCV 1h/1m, Mark, funding settlement history, historical contract rules, security master with classifications/listings/delistings, and sequence-consistent Quotes/L2 for VERIFIED execution. Missing funding is never zero. Current contract metadata is not historical proof.

## Implemented contracts

Causal reads select the latest revision available by decision time, never a later revision. Conflicting observations at the same availability time fail closed. Universe construction requires a daily security master and the prior 30 completed UTC days. Incomplete historical metadata explicitly yields PRELIMINARY quality. Unknown classification is ineligible; no current Top-20 feed is used for history. Synthetic tests carry synthetic-fixture provenance; VERIFIED in a fixture is a test input and is not a claim about real market data.
