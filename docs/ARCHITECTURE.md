# Architecture

Public data → causal records → historical universe → signal engine → risk reservations → deterministic intents → execution → ledger → reporting.

The event-driven reference engine owns research. Freqtrade will be the sole PAPER order authority. Signal logic will be shared. No LIVE path is authorized. Last and Mark are separate event streams. SQLite WAL will provide the transactional journal.

Implemented through Milestone 2: immutable domain primitives, Decimal helpers, canonical IDs and transactional SQLite WAL journal. No exchange order sender exists in the core. A PREPARED intent must atomically become UNKNOWN before dispatch. After restart, UNKNOWN is reconciliation-only; there is no resend path. Full identities/digests are retained alongside shortened client IDs. Symbol state remains separate from global pause. Remaining engines are not implemented yet.

## Client order identifiers

Binance USD-M official New Order documentation was checked on 2026-09-19: client IDs allow up to 36 characters. PVB-24 uses a four-character prefix plus 32 SHA-256 hex characters, with collision detection and full identity persistence.

Source: https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Order

## Streaming signal core (Milestone 4)

Indicators retain the earliest valid ATR seed and recursively update using completed contiguous true ranges. At a gap, no true range spanning unknown candles is invented; ATR state is preserved, transition history is unknown, and 720 new contiguous bars are required. This implements UD-02's valid-TR and complete-window rules. Revised/out-of-order inputs require an explicit as-of history rebuild and cannot silently mutate already emitted decisions.

Each frame stores its actual evaluation time; a decision cannot be backdated ahead of that computation. Indicators do not encode universe/risk acceptance in breakout state. A false-to-true transition rejected for volume is consumed by the next candle's state and cannot be chased. The reference/paper signal interface is the same function.
