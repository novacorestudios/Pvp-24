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


## Open account reconciliation (Milestone 8E)

OpenReconciler checks causal account cash, owned quantities, effective rules, fresh Mark valuations, terminal IOC evidence, confirmed protection and the current minute risk sample. It freezes actual entry risk from confirmed VWAP, fees and the original cost assumptions, retaining the initial stop even after confirmed trailing tightening. Only confirmed reduced quantity releases proportional reserved risk. Account proof failures persist an entry pause; foreign positions are rejected without producing orders for them.

Actual isolated collateral feeds liquidation repair. Portfolio/cost breaches request a full reduce-only close when residual compliance cannot be proved; existing unknown close intents prevent duplicate requests. Entries remain blocked until closure outcomes are resolved. Unsent zero-fill reservations can be canceled atomically, while dispatched unknown entries require outcome evidence. Source-specific account/Mark freshness limits remain explicit caller inputs requiring a frozen run policy. These synthetic tests do not establish exchange validation or operational PAPER readiness.


## Causal replay and preliminary execution (Milestone 9A)

Replay seals complete availability-time batches. Event time sorts only inside a batch already available to the engine. A complete comparable venue sequence overrides conservative same-time priority; incomplete or different-domain sequences do not. Unresolved liquidation/protective-fill order increments an explicit ambiguity counter. Duplicate identities are inert, changed identities and unseen backdated input are rejected, and a failed callback requires checkpoint recovery. This in-memory scheduler is not itself an atomic persistent account adapter.

The preliminary entry model freezes decision quantity and completed-input volatility/volume, then uses a separate minute-open observation without future OHLC extrema or volume. Only the first minute strictly after decision is eligible. The 90-second deadline, price bounds, IOC cap and participation still apply; book age, spread, depth and partial fills stay UNVERIFIED. No limit-touch fill model is provided. Aligned completed LAST/Mark bars use adverse liquidation-before-stop ambiguity; stop gaps use the worse opening price, and partially owned/partially protected bars require finer data. Synthetic liquidation references use adverse Mark extrema for sensitivity, not a claim of executable LAST or verified venue fills. These components are not yet a complete portfolio backtest and no historical performance has been computed.


## Atomic shared-core account replay (Milestone 9B)

AccountReplay applies each delivery, its ledger/protection/risk effects and a deterministic output receipt within one SQLite transaction. Journal reducers now nest through savepoints so an outer failure cannot commit only part of a fill. A failure persists a separate entry pause. Receipts return the same output after restart, preserving replay trace identity without duplicating cashflows or actions. No network I/O belongs inside these transactions.

Explicit deliveries now route confirmed fills/liquidations/funding, separate Mark observations, minute risk sampling, hourly LAST indicators, owned order outcomes, close-based exits and trailing requests into shared cores. Original signal channels are frozen before fills. Terminal/full outcomes require confirmed quantities; stop acknowledgements require dispatched owned intents and matching protection evidence. A partial terminal close may issue only its uncovered remainder; pending unknown exits prevent duplicate requests from risk or hold-time decisions. Late entry economics that differ from the frozen exit basis require reconciliation. Trailing requests remain separate from acknowledgements.

This is an integration layer for explicit normalized input events, not a historical performance result. Reference signal-batch/entry orchestration, automatic simulated order authority, full data adapter and operational Freqtrade integration remain unfinished. Replay labels alone do not certify VERIFIED source coverage or exchange liquidation behavior. The scheduler remains in-memory; a restart reloads source events and uses durable account receipts rather than fabricating a partial in-memory state.


## Ranked shared signal and entry planning (Milestone 9C)

SignalService reads the same persisted Indicators, historical Universe, owned pending/open positions and actual exit cooldowns for reference and future paper use. It waits for the complete hourly batch or the fixed 30-second deadline and delegates Alpha to signal_batch. AccountReplay records these decisions without creating a second signal implementation.

EntryPlanner consumes the ranked batch once, sizes each candidate against the portfolio updated by earlier accepted signals, and atomically records its reservation, ENTRY intent, protection ownership, original channels and dispatch deadline. Risk samples must be current; unresolved account gates, future inputs, price bounds, IOC caps, participation, quality and all existing sizing constraints remain enforced. The immutable source snapshot identity binds quantity-sensitive quote/margin callbacks; adapters must supply genuinely causal market-feasibility models, including VERIFIED book gates. The planner does not infer book coverage from a quality flag.

Receipts preserve identical output after restart and reject changed attempts to consume the same hourly batch. Failure while registering ownership rolls back the entire batch. Full signal decisions, input provenance and rejection/sizing outcomes are retained for later logs. No orders are sent by planning; dispatch must revalidate current market/account state and the deadline. Automatic reference execution, the complete replay runner and operational paper authority remain pending.


## Preliminary synthetic venue (Milestone 9D)

PreliminaryVenue now freezes entry proxy inputs before execution, consumes the first permitted minute open, applies adverse price-tick rounding, books explicit synthetic fills/fees and terminal IOC outcomes through AccountReplay, and separately acknowledges owned protective intents. Current account/risk gates are checked at dispatch. Unsent rejected entries are canceled with no fee or cooldown. UNKNOWN intents without an existing matching synthetic receipt require reconciliation and are never resent.

Requested market exits use a causal executable minute-open reference and adverse proxy slippage, bounded by confirmed remaining quantity. Receipt replay after restart preserves the original outcome. All synthetic venue effects commit atomically because this adapter has no network side effects; this transaction pattern must not be used to claim external PAPER dispatch before its write-ahead commit. Tests now exercise the complete shared-core signal → reservation → modeled entry → protection acknowledgement → restart → 72h exit → ledger cash identity path.

This adapter deliberately supports PRELIMINARY only and declares book age/spread/depth/partial-fill fidelity UNVERIFIED. It is not a full historical runner: automatic protective-stop/liquidation bar resolution, account/collateral observations, complete source ingestion, quality/coverage manifests and Freqtrade sole PAPER authority remain integration work. Synthetic successful cycles are not historical performance evidence.


## Preliminary collateral and adverse bar execution (Milestone 9E)

SyntheticCollateral requires an explicitly selected BASE_MARGIN_RELEASE_ONLY policy and manifest identity before cashflows. For an open position, remaining cost-basis margin is released proportionally on partial exits; realized PnL, actual fees and settled funding remain in its collateral until full closure. Mark coverage is validated separately. This is a declared preliminary assumption, not exchange collateral evidence, and it cannot satisfy VERIFIED acceptance. It feeds the existing OpenReconciler using actual modeled fills and unchanged original risk.

The bar execution adapter requires separate completed LAST/Mark candles, pre-bar execution/liquidation inputs and already-acknowledged full protection. Gaps use the adverse executable open plus stop slippage with doubled impact once. Unresolved stop/liquidation overlap chooses liquidation, records its explicit all-in fee and adverse Mark reference, and increments the persistent ambiguity count once. Bar-end fill timestamps are explicitly assumptions; exact intrabar time is not claimed. Intrabar entry, quantity or protection changes require finer data. A failed/unsupported bar is not a successful zero-liquidation result.

Historical funding coverage, actual exchange tiers/fees/collateral validation, latency-path coverage and full historical replay remain outstanding. The explicit fee-rate/manifest arguments are not permission to mark guessed exchange history VERIFIED. No historical performance or paper trading has run.


## Reproducible reference integration runner (Milestone 9F)

scripts/smoke_reference.py now runs a deterministic synthetic reference lifecycle with 720-hour indicator warmup, ranked signal/entry planning, dense minute risk samples, explicit modeled entry/protection, causal account proof, adverse bar checks, a mid-run SQLite reopen, early-failure exit and final cash identity. The run processes 964 delivered events. Inputs and a manifest are written before account execution; the manifest records frozen policy, baseline config hash, Git SHA, dirty-worktree status, source-tree hash and exact synthetic data SHA-256. Existing output directories are never overwritten.

The run records a trace, ledger-backed summary and account journal under the requested output directory. It reports ENGINE_INTEGRATION_SMOKE, historical_performance=false, acceptance_status=NOT_EVALUATED, paper_ready=false and zero exchange orders. Future-appended fixture data change the source manifest but leave the historical trace, entry, exit and ledger identical. CI invokes this actual command after governance checks. This is not a six-year backtest, general historical file loader, VERIFIED execution run or evidence of profitability. Historical source/coverage integration remains pending.


## Freqtrade shared-core strategy and parity (Milestone 10A)

PVB24Executor now loads through the actual pinned Freqtrade StrategyResolver. SharedPaperBridge delegates causal normalized events, signal batches and entry planning to the existing core; no Alpha is recomputed from native float-valued dataframes. Native entry/exit flags are zero and native confirmations refuse dispatch, preventing a second order path. The dedicated paper config is explicitly non-operational and rejects LIVE, changed baseline controls and changing quality after account binding. No fee/price float coercion enters the Decimal core.

The pinned Freqtrade create_order dry-run branch calls create_dry_run_order without forwarding time_in_force or reduceOnly. Its native dry-run fill model also uses its own price-crossing/full-fill assumptions. Therefore native dry-run cannot silently substitute for PVB24 execution. A separately qualified PAPER transport remains necessary; setting operational_ready=true is rejected by the current bridge. This milestone proves strategy loading and signal/intent parity, not operating PAPER or order/venue parity.

The actual Freqtrade 2026.8 loader, configuration validation, startup callback, fixed-fixture event/signal/intent parity, native-order blocking and LIVE rejection were executed successfully offline. CI now repeats the parity script. Source Freqtrade remains pinned and unmodified. During this session its copied virtualenv had a broken circular interpreter symlink; the generated link was repaired and the locked bootstrap reinstalled successfully. No historical source, alpha threshold or dependency pin changed.


## PAPER entry write-ahead boundary (Milestone 10B)

PaperDispatch validates owned entry intents against required account and current-minute equity streams, the original 90-second deadline, causal unchanged contract rules, synchronized fresh L2, spread/price/IOC/participation limits and a quote matching the book. It recalculates risk, margin and liquidation feasibility while excluding only its own pending reservation; original quantity/leverage and committed fee/funding/risk capacity cannot be increased. A second clock/book check rejects validation that itself becomes late. Failed validation leaves the unsent intent PREPARED and its reservation held for reconciliation.

An exclusive Linux flock on the journal inode prevents multiple cooperating PAPER hosts, including path aliases. Backend instance identity/quality are frozen across restart. Before backend I/O, the complete validation evidence, exact Decimal LIMIT/IOC ticket and UNKNOWN dispatch claim commit in one transaction. External calls inside an existing transaction are refused. A lost response, process interruption or missing lookup leaves the outcome unresolved and never authorizes another submission. Valid acknowledgement binds unique client/venue order identities but creates no fills, terminal outcome or risk release.

22 new tests cover a separate-connection view of the committed ticket before I/O, timeout-after-acceptance/restart/absent lookup, competing authorities, mandatory gates, changed economics, validation latency, malformed acknowledgements, precommit rollback and interruption before backend I/O. These tests use an explicit synthetic backend. The backend protocol is a trusted implementation contract, not evidence that a real model is qualified. The operational bridge remains blocked. Protective-stop/reduce-only/cancel transport, a concrete durable PAPER backend, process integration and source-backed execution fidelity remain pending. No exchange orders or historical performance runs occurred.


## PAPER protection, exit and cancellation tickets (Milestone 10C)

The same exclusive PaperDispatch authority now translates owned PROTECT, EXIT_MARKET, CANCEL_PROTECTION and CANCEL_ENTRY intents. A separate explicit backend contract requires reduce-only STOP_MARKET with CONTRACT_PRICE/LAST, reduce-only MARKET and owned-ID cancellation. These paths remain available while entry risk/account gates are paused. They reject backdated account evidence, changed/stale action payloads, changed stop proposals and quantities exceeding the actual remaining position. Already-dispatched unresolved exits reserve their not-yet-filled quantities, so different client IDs cannot duplicate closure of the same quantity.

Cancel requests require a proven target venue ID. An unknown entry with no mapped venue ID must first be queried. Old protective orders can be canceled only when a different acknowledged stop covers the remaining quantity at the desired stop, or the owned position is flat. Ticket/UNKNOWN writes precede I/O just as for entries; a timeout/restart never permits resubmission.

Action request acceptance only records immutable transport/venue identity. It intentionally leaves the action unresolved until explicit active-stop, fill or cancellation evidence reaches the shared account core. This prevents acceptance from masquerading as stop activation/cancel completion, and prevents transport ACK records from conflicting with richer core STOP_ACK evidence. Lookup of a stop after core confirmation is idempotent. No reservation or actual position quantity changes on transport acceptance.

Eight added tests exercise shared-core entry fills and STOP_ACK integration, paused-entry emergency action dispatch, replacement-before-cancel, cancellation of the only stop being refused, duplicate exit quantities, stale protection after partial reduction, lost action replies/restart, unknown entry cancellation lookup and contract/clock rejection. A concrete durable PAPER backend and normalized cancellation/fill evidence ingestion are the next work; operational_ready remains false. No historical performance or exchange-model qualification is inferred from these synthetic tests.


## Owned PAPER execution evidence (Milestone 10D)

PaperEvidence ingests immutable events from the bound PAPER backend only, with explicit source identity, quality, event/available times and canonical Decimal records. Submitted-order fills require the exact committed client ticket, mapped venue order, owned position/symbol and matching execution side/reduce-only flags. Transport acceptance never supplies an inferred fill. Event receipts and all nested ledger/protection/order effects commit atomically; duplicate evidence survives restart, changed economics conflict, and failures preserve a separate entry-reconciliation pause after rollback.

Terminal outcomes require cumulative venue fills to equal the already-ingested actual fills for that exact order; a FILLED outcome requires its complete submitted quantity. Cancel confirmation first settles the proven target terminal outcome, then acknowledges the cancel request in the same transaction. A cancel/fill race cannot erase a partial position or release its original risk reserve. The shared AccountReplay now handles STOP_TERMINAL: rejected, canceled or filled stops cease to supply coverage, and losing the last protection requests a bounded safety close. Repeated query/cancel evidence preserves an already-proven terminal outcome.

Authoritative overfills are retained in cash/quantity evidence and force safety reconciliation/closure rather than being discarded. Explicit forced-liquidation evidence is anchored to the owned entry position and a separate unique forced order ID; it enters the shared liquidation/fee ledger visibly. It is not inferred from a price bar or asserted to validate an exchange liquidation model. Unrequested foreign orders remain blocked.

Thirteen new tests cover a full entry/active-stop/replacement/cancel/exit/flat-cash proof, cancel/fill races with missing-fill rejection, identity/side/time/source validation, rejected-stop emergency close, restart deduplication, atomic rollback after nested fill effects, overfill retention and explicit liquidation loss/fee visibility. The full local suite has 301 passing tests. A concrete durable PAPER backend, market/account feed policy, model qualification and live Freqtrade process integration remain pending; operational_ready=false and LIVE disabled.


## Durable preliminary L2 entry model (Milestone 10E)

L2PaperVenue is now a concrete socket-free PRELIMINARY entry backend, separate from the account journal. Its identity/scope/model/manifest policy is immutable across reopen. Source books and fee/contract terms are stored causally. Visible depth is consumed by exact Decimal LIMIT/IOC fills, and only a later explicit absolute level update or advancing resnapshot replenishes it. Duplicate source events never refill consumed depth; sequence gaps persist an unsynchronized book before raising. Book/ticket contract filters and source freshness remain active.

Each accepted or rejected request, complete input snapshot, actual modeled per-level fill/fee, terminal IOC outcome, backend position quantity and ordered evidence stream commit before the backend returns. A source cursor allows the account consumer to replay only durable evidence after its own commit. Backend lookup after restart returns the original receipt; a lost response never produces another fill. The model labels every event PRELIMINARY and cannot bind to a VERIFIED dispatch host.

OrderRejected is a distinct durable refusal receipt. A backend can refuse an order that expires after the host's dispatch claim without pretending it was accepted before its deadline. The account remains unresolved until its explicit REJECTED terminal evidence is ingested, after which flat cash/quantity reconciliation can release the reservation. A missing lookup still never authorizes resubmission or risk release.

Eight tests verify actual modeled per-level fees, partial IOC depth consumption and replenishment, source cursors, two-database timeout/reopen recovery, deadline refusal and flat reconciliation, persisted book gaps, atomic backend failure and immutable policy/quality. All 309 local tests and governance checks pass. This backend currently executes entry only. Protective/market exit/cancel execution, full fee/funding/collateral/liquidation behavior, source-backed execution qualification and sole Freqtrade process integration remain pending. No operational PAPER or historical performance is claimed.


## Durable PAPER protection and reduction execution (Milestone 10F)

The concrete L2PaperVenue now accepts owned STOP_MARKET/LAST, reduce-only MARKET and cancel tickets. Active-stop evidence is committed with its receipt, and a stop requires an explicit frozen LAST freshness policy and a current valid LAST observation; already-crossed/stale stops are refused with a durable terminal result, allowing the shared core to request emergency closure. Only a post-activation LAST observation can trigger a stop. Book changes alone do not trigger LAST stops. Gap execution uses actual visible book levels, not an invented fill at the stop price.

Market and triggered-stop fills are bounded by the backend's current owned position and consume visible depth. Insufficient visible depth leaves the unfilled residual PENDING; later explicit depth updates continue the same order with unique fill IDs/sequences. No automatic resubmission or invented full closure occurs. Simultaneous stops use acceptance order as a declared PRELIMINARY modeling assumption, and reduce-only execution prevents multiple active stops from reversing the position. Cancellation records the target's actual terminal outcome, including when a fill wins the race.

The model policy is versioned L2_VISIBLE_ORDERS_LAST_STOP_V2 and cannot reopen an old/changed policy silently. LAST freshness, pending-market-depth behavior and simultaneous-stop ordering are frozen in the model record. Mutation clocks are persisted monotonically. Exit fee terms are explicit; unavailable execution terms/depth retain pending status. No numerical production freshness default was invented: tests explicitly freeze a one-second synthetic LAST policy. The account adapter now accepts explicit zero-fill cancel-request refusals without altering the target order.

Nine tests cover replacement/cancel/market-exit accounting, LAST-only gap stops, partial pending exits resumed by new depth, crossed-stop emergency closure, stop/cancel races, reopen recovery, stale LAST, pre-activation trade exclusion, clock/policy rejection and lost stop-response lookup. The full local suite has 318 passing tests. Funding/collateral/liquidation execution modeling, feed completeness, durable process cursor/dispatch orchestration and sole Freqtrade startup/parity remain pending. Operational readiness and LIVE remain disabled; this is not verified exchange behavior or historical performance evidence.


## Preserve valid ranked-batch reservations during reconciliation (Milestone 10G)

Executor integration exposed an existing reconciliation defect: confirming the first filled symbol canceled every other unsent entry in the already-accepted batch. OpenReconciler now preserves intact PREPARED reservations in their original acceptance order when their deadline, current risk fraction, slots, directional/total risk, notional, margin and collateral commitments still permit them. It keeps exact original quantities/identities; dispatch still revalidates quotes/book/time. Expired or no-longer-feasible unsent reservations are canceled locally with terminal zero-fill ownership and no fee/cooldown. UNKNOWN entries are never treated as unsent and keep the account paused with all reservations retained.

AccountObservation.free_collateral is explicitly the venue-spendable balance before local strategy reserves. Reconciliation subtracts remaining open-position exit/slippage/funding reserves and all kept pending entry margin/cost commitments exactly once. Realized entry fees are already in cash and are not reserved again. Repeating an observation does not cumulatively deduct reserves. This aligns reconciliation with the existing reservation/dispatch free-collateral contract without changing Alpha or thresholds.

Four regression tests exercise two ranked symbols through the first actual fill/stop confirmation, preservation of the second reservation, exact commitment accounting/repeat invariance, expiry without fees/cooldown, loss of current collateral capacity and unresolved second-order retention. The full local suite has 322 passing tests. The actual reference smoke command still processes 964 events with unchanged trace hash 14d443af600ab971927ef90121ba9acf49ca62645c73c21cb44dbdd1fdb5f6f0, restart verified and zero external orders. Cursor/dispatch orchestration and Freqtrade process integration are the next tasks; no operational or historical performance readiness is claimed.


## Durable PAPER evidence recovery (Milestone 10H)

PaperSession binds the concrete PRELIMINARY L2 model's policy and account scope to a durable consumer checkpoint. Account evidence and its ledger/protection/action effects commit before the source cursor advances in a separate transaction. A crash between these commits replays the immutable account receipt without duplicating fills or action identities. Every cursor stores the last source event's identity/hash and requires its matching account receipt; a replaced, truncated or changed source fails closed. Bounded pages preserve ordering and retain backlog instead of silently skipping events.

Missing transport receipts are recovered by owned client-ID lookup only. An absent lookup preserves UNKNOWN and all reservations. Known acceptance still requires explicit active/terminal execution evidence. Recovery leaves account pauses intact; it cannot substitute for cash, collateral, protection and minute-risk reconciliation. A confirmed active stop is not treated as an unresolved entry, while pending exit residuals remain unresolved and reserve their quantity. Valid protective/safety requests remain dispatchable after available evidence is drained.

PaperDispatch now commits an account entry pause with the entry ticket/UNKNOWN claim, before backend I/O. It also refuses new entries while any unknown execution or nonterminal entry/exit acknowledgement remains, even if a stale gate still says ready. This closes the lost-response interval before the first fill is delivered.

Eleven regression cases cover bounded pages, two-database reopen after a lost reply, interruption after account commit but before cursor commit, atomic account failure, absent lookup, changed/truncated source anchors, missing account receipt, pending-exit protection and unresolved-entry dispatch blocking. All 333 local tests pass with formatting/lint and provenance checks. Automatic action retirement/pumping and sole Freqtrade process binding remain next; operational_ready=false, LIVE disabled, no historical data/performance or external order execution.


## Bounded action pump and Freqtrade local execution parity (Milestone 10I)

The shared PAPER session now pumps committed actions in deterministic priority: reduce-only exits, protection, entry cancellation, then old-stop cancellation, preserving creation order inside each class. It drains available evidence before action validation and after each backend response. Work budgets return explicit pending/deferred requests for the next loop; unresolved submitted requests are queried and never automatically resent. A validation failure before the dispatch claim retains the original PREPARED intent and pauses entries while other valid safety actions can proceed.

Only proven unsent actions can be retired locally. Retirement verifies ownership, absence of a transport ticket/dispatch claim and current confirmed account evidence, then records an immutable reason/position/intent proof with never_dispatched=true. Flat positions, reduced quantities, superseded stop proposals/cumulative protection and already-terminal cancel targets are handled explicitly. An oversized unsent exit produces a separate bounded shared-core successor identity for quantity not already committed to other exits; no sent order is silently resized and no reservation is released by retirement.

PVB24Executor can explicitly bind LOCAL_PRELIMINARY_L2 research transport and uses the same session during its loop callback. The default committed config remains blocked; operational_ready=true is still rejected, native trade confirmations remain false and no native dry-run substitution occurs. The bridge drains durable execution before new core inputs, prevents a second authority, rejects changing quality/transport after binding and closes its journal lock explicitly. This is local model hosting through the real strategy class, not a complete running FreqtradeBot market-feed process.

The actual pinned Freqtrade StrategyResolver and loop callback passed expanded offline execution parity: two separate account/model paths produce identical intents, ledger/protection/cursor snapshots, order outcomes, fills and fees through entry, initial protection, replacement-before-cancel, reduce-only exit and terminal stop cleanup. Each path models six requests and two fills, with zero external orders. Execution evidence hash: f434633cf4dfef2025708f646550502946fc62e1f85a924c948399206190baa1. The synthetic contract tick is corrected from 0.1 to 0.01 so its existing 101.21 price is executable; signal hash is unchanged and fixture intent hash is now 30182c81e794ccc4d112c4c8bc9c4ef9eca4364ddee68969be0e593c178f2129. Frozen Alpha/config/source hashes are unchanged.

Nine new tests cover complete action lifecycles, stale unsent requests, exit priority, pending partial reductions with residual protection, distinct bounded successor exits, crossed-stop refusal/safety closure, lost stop replies and work-budget continuation, cancel/fill races and explicit guarded bridge binding. All 342 local tests pass with Ruff and provenance. The restored dependency environment had a missing/circular generated Python link; it was repaired and the locked install rerun without changing Freqtrade source. Feed/account/collateral/funding/liquidation qualification, operational process startup and protection-acknowledgement timing policy remain outstanding. Historical data acquisition/evaluation has not started; PAPER NOT READY and LIVE disabled.


## Frozen protection timeout and framework cleanup recovery (Milestone 10J)

ProtectionWatchdog accepts an explicit positive acknowledgement timeout and policy ID, frozen in the account journal before the first PAPER transport dispatch. No production numerical default is invented; sessions without this policy remain unqualified research only. Once configured, reopening cannot remove/change the policy, and in-memory mutation is rejected. The timeout starts at the durable PROTECT ticket timestamp and survives restart. Available evidence is drained first, so a recovered active-stop acknowledgement prevents a false timeout.

At or after the frozen deadline, a still-UNKNOWN stop with a confirmed remaining position lacking full current protection causes a durable safety pause and a bounded shared-core exit for only quantity not already committed to other exit requests. A prior pending close is not duplicated. The unknown stop is neither resent nor declared canceled, quantities/reservations are not released, and absent book/fee terms leave the exit pending rather than fabricating closure. Timeout decisions are idempotent across repeated callbacks/restart.

PVB24Executor now overrides the pinned framework's ft_bot_cleanup hook, invokes the base cleanup and always releases its local PAPER authority in a finally block. The actual offline Freqtrade parity command now injects a base cleanup failure while a modeled protective stop is active, re-instantiates the strategy, rebinds the same account/model journals and continues through replacement/cancel/exit with identical economics. This proves strategy lifecycle recovery and exclusive-lock release, not full exchange-connected FreqtradeBot startup.

Seven added tests verify the exact timeout boundary, no repeated stop/exit request, pending-close reservation, unchanged restart deadline, immutable/required-before-dispatch policy, mutation rejection and acknowledgement recovery before timeout. All 349 local tests pass with Ruff/provenance. Expanded pinned-framework parity passes with unchanged execution evidence hash f434633cf4dfef2025708f646550502946fc62e1f85a924c948399206190baa1, six modeled requests/two fills per path and zero external orders. Synthetic fixtures explicitly choose one second; production feed/latency policy is not qualified. Operational process/feed/account qualification and historical data/evaluation remain outstanding. PAPER NOT READY; LIVE disabled.


## Full offline FreqtradeBot lifecycle (Milestone 10K)

The expanded parity command now supports --framework. It constructs the real pinned FreqtradeBot, initializes an isolated native persistence database and its actual wallet/pairlist/data-provider/strategy/RPC infrastructure, calls startup, executes three full process cycles with the shared PAPER session, and calls cleanup. Only the exchange boundary is replaced with a strict explicitly synthetic fixture. Socket connections and DNS resolution are forbidden and counted; native exchange order/stop calls fail and are counted. Messaging endpoints are absent, so framework status logging sends no external notification.

Shared Decimal events still supply all Alpha/account evidence. The native fixture deliberately provides no OHLCV rows; empty-candle warnings do not substitute fake historical prices or create native trades. The actual process callback resumes an active modeled stop after strategy reinstantiation and carries replacement-before-cancel and reduce-only closure through the same shared core. The smoke verifies no native trades/orders/network attempts, three data-provider refresh/process cycles, closed exchange fixture, identical ledger/protection/cursor snapshots and six modeled requests/two fills per path. Execution evidence hash remains f434633cf4dfef2025708f646550502946fc62e1f85a924c948399206190baa1.

Both the ordinary strategy smoke and the full-framework offline command pass locally. Ruff/provenance pass; production core is unchanged from the 349-test Milestone 10J suite, and CI now repeats the full framework command. The first framework fixture attempt failed because a disabled Telegram config still requires credential-shaped schema fields; the unused messaging sections were removed instead of supplying credentials. No production config or frozen Alpha changed.

This proves full offline framework lifecycle integration, not a public Binance feed connection, exchange-model qualification or operational PAPER readiness. The next work is official data acquisition/provenance and causal normalized source integration. Historical universe/rules/Mark/funding/L2 coverage, collateral/liquidation qualification, six-year evaluation, acceptance and the 90-day paper record remain incomplete. Final Test stays locked. PAPER NOT READY; LIVE disabled.


## Official archive boundary (Milestone 11A)

ArchiveRequest restricts monthly USD-M source identity and refuses Final Test months before I/O. The acquisition layer validates official filename-bound checksums and writes immutable content-addressed ZIPs, checksums and attempt records. load_acquired rechecks hashes, decoder identity and normalized coverage before consumption. The strict decoder emits separate LAST/Mark candles with modelled +2s availability and exact decimals. FundingArchiveRow is raw settlement evidence, intentionally distinct from a contiguous FundingSettlement index. Acquisition metadata and dataset hashes do not certify historical publication timing, security eligibility, trading rules or executable liquidity. See DATA_PROVENANCE.md and DATA_COVERAGE.md.
