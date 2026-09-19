# Architecture

Public data → causal records → historical universe → signal engine → risk reservations → deterministic intents → execution → ledger → reporting.

The event-driven reference engine owns research. Freqtrade will be the sole PAPER order authority. Signal logic will be shared. No LIVE path is authorized. Last and Mark are separate event streams. SQLite WAL will provide the transactional journal.

Implemented through Milestone 2: immutable domain primitives, Decimal helpers, canonical IDs and transactional SQLite WAL journal. No exchange order sender exists in the core. A PREPARED intent must atomically become UNKNOWN before dispatch. After restart, UNKNOWN is reconciliation-only; there is no resend path. Full identities/digests are retained alongside shortened client IDs. Symbol state remains separate from global pause. Later sections describe subsequent implemented components; execution/accounting/backtest integration is still pending.

## Client order identifiers

Binance USD-M official New Order documentation was checked on 2026-09-19: client IDs allow up to 36 characters. PVB-24 uses a four-character prefix plus 32 SHA-256 hex characters, with collision detection and full identity persistence.

Source: https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Order

## Streaming signal core (Milestone 4)

Indicators retain the earliest valid ATR seed and recursively update using completed contiguous true ranges. At a gap, no true range spanning unknown candles is invented; ATR state is preserved, transition history is unknown, and 720 new contiguous bars are required. This implements UD-02's valid-TR and complete-window rules. Revised/out-of-order inputs require an explicit as-of history rebuild and cannot silently mutate already emitted decisions.

Each frame stores its actual evaluation time; a decision cannot be backdated ahead of that computation. Indicators do not encode universe/risk acceptance in breakout state. A false-to-true transition rejected for volume is consumed by the next candle's state and cannot be chased. The reference/paper signal interface is the same function.

## Risk foundations (Milestone 5A)

Cost estimates use Decimal context 34 and retain separate per-base-unit components. Arrival-side execution shortfall affects the 25% cost gate, never the sizing loss a second time. Initial stops round away from entry. Funding uses completed as-of revisions and actual interval lengths; a causal source completeness watermark is mandatory because the last row alone cannot distinguish a missing settlement from a still-running interval. Missing history and gaps reject. No receipt offsets adverse reserves.

Portfolio views aggregate one open/pending reservation per symbol. The adapter must provide current causal Mark valuation for open quantity, expected entry for pending quantity, and exchange-obligated initial margin. Free collateral is already net of existing commitments. Stop changes cannot release reserved initial risk; only confirmed remaining quantity scales the original reservation. These pure models do not yet provide a transactional reservation coordinator or order authority.

## Risk solver and reservation transaction (Milestone 5B)

The solver searches quantity-step units downward from a necessary risk upper bound, recomputing quote/cost/margin/liquidation for every candidate, with at most five outer passes and two consecutive identical accepted quantities required. Downward enumeration deliberately avoids assuming that rounding, tier jumps and cost-ratio feasibility are globally monotonic. It can be expensive for fine increments; no latency qualification is claimed. Quote adapters return no quote for quantities failing execution/liquidity feasibility. Contract count increments convert to base units before cost calculations.

Each candidate checks frozen risk/notional/cost constraints, then ascending leverage 1..5 against exchange tier limits, initial margin and free collateral obligations. PRELIMINARY alone may use theoretical margin. VERIFIED additionally requires effective verified rule history, an externally validated liquidation model flag, verified quote evidence and an exchange margin callback. No available fixtures establish VERIFIED status yet.

Liquidation is reconstructed from isolated collateral plus signed unrealized PnL equal to tier maintenance notional minus cumulative deduction, choosing a self-consistent tier at the liquidation Mark price. Missing/invalid tiers and unsupported roots reject; no guessed current tiers replace historical ones. Collateral is net of entry fees and adverse funding reserve for the pre-entry check. Liquidation fees/venue-specific adjustments still require safe exchange validation before VERIFIED.

References inspected on 2026-09-19:
- Official pinned Freqtrade `freqtrade/exchange/binance.py`, `dry_run_liquidation_price`, commit `9f10e357a93c1dcf10c2a2b367659214d89c073e`. This is a formula cross-check, not exchange-value validation.
- [Binance notional and leverage bracket schema](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/account): effective adapter inputs include notional floor/cap, maintenance ratio, cumulative deduction and leverage limit. Account adjustments must be reflected in effective brackets.
- The Binance FAQ linked by Freqtrade could not be retrieved; no successful FAQ verification is claimed.

`Reservations.reserve` compares the journal portfolio revision, rechecks capacity, and atomically writes both pending reservation and ENTRY intent. Any concurrent revision or write failure rolls back the whole transaction. Dispatch remains the separately durable UNKNOWN transition. Subsequent execution reconciliation must update/release reservations with actual fills. Post-fill compliance has a fail-closed action interface: reduction may only decrease quantity; unknown compliance requests full close. Its caller must model the real residual collateral and exit costs, never assume a freshly opened replacement position.
