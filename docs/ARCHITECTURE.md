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

## Execution market models (Milestone 6A)

USD-M snapshots remain unusable until a websocket event bridges the snapshot update ID; subsequent updates require previous-final sequence continuity. Levels are absolute quantities, zero removes a level, and removing an unknown level is valid. Invalid sequences or crossed books require a new snapshot. Both event and receipt age must be within 500ms.

IOC limits use the strictest channel, signal-close and per-level impact cap, with long rounding down and short rounding up. Previews enforce breakout validity, spread and requested-notional participation. Partial sweeps are explicit; no inaccessible remainder is filled. Replay consumption remains unavailable until the affected level receives a later absolute update; unrelated updates and duplicate sequence messages cannot replenish it. Haircut stress applies proportionally.

PRELIMINARY minute inputs require sixteen contiguous completed closes for fifteen log returns and only the last fifteen quote volumes. The latest completed minute must be causally available. The proxy retains UNVERIFIED labels for book age/spread/depth/partial fills; it does not manufacture L2. Entry/stop proxy prices embed slippage once. The event-loop integration must supply the first minute open strictly after decision, rather than a future candle close.

[Official Binance local-book procedure](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/How-to-manage-a-local-order-book-correctly) inspected 2026-09-19. This module does not connect a websocket or send any order.

## Confirmed-fill protection (Milestone 6B)

The position state machine deduplicates complete fill identities, computes actual cumulative VWAP and protects every confirmed residual quantity. A stop request is not protection evidence. A valid replacement must be acknowledged with the requested quantity/trigger, reduce-only semantics and CONTRACT_PRICE reference before the prior stop is canceled. A late acknowledgement of obsolete protection is canceled after current protection exists. Lost/unconfirmed protection emits a full reduce-only close request plus a safety pause; the global overlay does not erase OPEN state.

A terminal zero-fill IOC returns READY without a six-hour cooldown. Actual late fills remain authoritative after a cancel/terminal notification and receive protection. A real full exit starts the six-hour cooldown at the confirmed exit timestamp. Late entry fills after an actual full exit trigger an emergency close. Confirmed over-reduction anomalies retain evidence and require reconciliation; the model never fabricates a reversing trade. Requested exits are bounded by known remaining quantity and are always reduce-only.

ProtectionStore atomically journals event evidence, resulting state and deterministic action intents. After a process restart, PREPARED actions can be claimed once; UNKNOWN actions remain reconciliation-only. There is no actual network sender. The adapter must invoke protection failure promptly when acknowledgement cannot be established; no arbitrary timeout is invented here. Ledger-backed account updates and post-fill collateral/fee calculations remain integration gates, so this milestone does not establish operational PAPER readiness.

## Close-based exits (Milestone 7)

The shared exit engine receives frozen confirmed entry economics and hourly LAST closes. Initial price risk remains fixed. Equal-time/pre-fill closes do not count; first-three-close failure uses inclusive channel boundaries, and sixth-close weakness uses strict close-MFE <0.5R. High/low extrema do not enter these calculations. The 72h timer starts at actual first fill and operates independently of missing candles. Missing eligible close sequences require reconciliation rather than silently advancing the counter.

Trailing activates at a completed close reaching 2R and uses highest/lowest eligible close minus/plus 3 current ATR. Tick rounding tightens, and neither acknowledged nor pending desired stops may widen. The engine keeps proposed and confirmed-effective stop timestamps separately; no historical bar acquires a stop calculated later. A crossed proposed trigger requests a full exit instead of pretending to install protection behind market price. Existing protective/liquidation fill precedence belongs to the event-loop integration in Milestone 9.

## Fill ledger and risk overlay (Milestone 8A)

The dedicated ledger records owned positions, immutable actual fills and explicit settlement cashflows. Views select only evidence received/available by the requested time. Confirmed fills are ordered by event time and exchange sequence where present; unresolved same-time ordering uses conservative reductions first and is counted. Missing entry evidence makes accounting fail closed until reconciliation, while the input remains preserved. Late evidence cannot rewrite an earlier as-of view.

Partial emergency exits allocate the then-remaining weighted cost basis. Later IOC fills add new actual cost to remaining basis, so realized plus unrealized PnL stays consistent even when entry and emergency exit overlap. Actual USDT fees are counted once per fill; negative fees remain rebates. Funding uses a unique settlement ID and explicit evidence of eligible boundary quantity; attaching it to a position does not deduct it again. Cash excludes notional, margin reservations, estimated funding and execution-shortfall diagnostics. Liquidation fills remain visible and their actual fees remain expenses.

Mark equity requires a caller-specified, precommitted freshness horizon and fails on missing/stale/conflicting data. No arbitrary Mark horizon is frozen by this implementation and no LAST substitution is available. Minute controls latch a -4% daily loss pause until the next UTC day, reduce new-entry risk at 10% drawdown until recovery of the original peak, and latch a 15% hard pause permanently in research. Safety pauses also survive midnight. A missing midnight baseline blocks entries rather than rebasing daily loss later. Gaps are counted, not hidden. Integrated account/reservation reconciliation and execution are still pending.

## Atomic account coordination (Milestone 8B)

AccountCoordinator registers protection ownership against an accepted pending reservation, then persists each fill into the ledger and protection state with its protective intents and an entry-blocking account gate in the same transaction. A write failure rolls back all four pieces. A duplicate fill or funding event does not create another expense or order. Standalone component stores remain useful for tests, but the integrated adapter must use this coordinator for owned account events.

Reservations now require an initialized, reconciled account gate. Fill/funding/terminal/protection events invalidate that reconciliation while prior risk reservations remain locked. Flat reconciliation requires matching actual cash, no ledger position, and proven terminal IOC outcomes; it may release reservations but never clear a safety pause. Late fills after an apparently zero-fill cancellation re-establish ledger/protection state and block entries again. Open positions require the forthcoming actual residual-collateral compliance path; there is no flat-account shortcut. This gate establishes reconciliation only; the adapter must additionally apply equity risk, data freshness and all normal entry gates.

## Actual-collateral liquidation repair (Milestone 8C)

The liquidation remedy takes actual isolated collateral net of charged fees/settled funding. For each candidate reduction it adds realized reduction PnL, subtracts the reduction fee and explicitly modeled collateral release, then recomputes the remaining position's tier-consistent liquidation against the unchanged original stop. There is no new-position sizing shortcut, leverage change or invented top-up. The greatest compliant quantity-step candidate is retained. Unknown projection provenance, future data or missing required verification fail closed to a full reduce-only close request. Synthetic retained-collateral and proportional-release fixtures produce deliberately different outcomes; neither claims actual venue collateral-release behavior. The helper handles liquidation distance only, leaving portfolio-wide post-fill compliance to account reconciliation.

## Durable risk actions (Milestone 8D)

AccountRiskService freezes the caller's source-specific Mark age and policy identifier before fills/funding are observed. It atomically records minute equity risk state and resulting cancel/close intents. A newly triggered daily loss pause cancels entries; a hard drawdown pause additionally requests reduction of owned open quantity. PREPARED entries are canceled transactionally without network dispatch, while UNKNOWN/ACKNOWLEDGED entries get deterministic cancellation intents for the executor. Outstanding unknown exit quantities are not resubmitted. Subsequent hard-pause samples request closure only of newly uncovered confirmed quantity.

Reservations compare their requested risk fraction to the durable overlay and reject paused entry states. ENTRY dispatch claims also consult existing account and equity-control streams. Protective and reduce-only orders bypass entry pause gates. The eventual operational executor must require initialized account/control streams, current sample freshness and the original signal deadline; the generic journal remains usable independently by component tests and is not itself a complete executor. Missing/stale Mark pauses entries, and risk-policy reconfiguration after observation is prohibited.
