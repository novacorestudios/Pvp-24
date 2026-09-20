# Handoff — Milestone 10D (owned PAPER execution evidence)

- Repository: novacorestudios/Pvp-24; branch build/pvb24-v1.
- Exact current HEAD: read the Git branch ref; main remains initialization only.
- Milestone 0 remote HEAD: f1d9ece4d4cc14d09adfe715d043ee58de437ad8.
- Milestone 0 CI: https://github.com/novacorestudios/Pvp-24/actions/runs/35422954155 — SUCCESS.
- Public-disclosure authorization: user explicitly approved publishing these files and will change visibility later. Do not request this approval again.
- Milestone 1: official Freqtrade 2026.8 / 9f10e357a93c1dcf10c2a2b367659214d89c073e installed; repeat locked install and offline dry-run config smoke passed.
- Local tests: 301 passed; Ruff lint/format passed. CI for this commit: check GitHub Actions after publication.
- Milestone 1 CI: https://github.com/novacorestudios/Pvp-24/actions/runs/35423197873 — SUCCESS.
- Milestone 2 CI: https://github.com/novacorestudios/Pvp-24/actions/runs/35423500106 — SUCCESS.
- Milestone 3 final CI: https://github.com/novacorestudios/Pvp-24/actions/runs/35423929247 — SUCCESS.
- Milestone 4 CI: https://github.com/novacorestudios/Pvp-24/actions/runs/35436419215 — SUCCESS.
- Milestone 5A CI: https://github.com/novacorestudios/Pvp-24/actions/runs/35436779986 — SUCCESS.
- Milestone 5B CI: https://github.com/novacorestudios/Pvp-24/actions/runs/35437127477 — SUCCESS.
- Milestone 6A CI: https://github.com/novacorestudios/Pvp-24/actions/runs/35437412947 — SUCCESS.
- Milestone 6B CI: https://github.com/novacorestudios/Pvp-24/actions/runs/35437666429 — SUCCESS.
- Follow-up: unacknowledged entry protection remains ENTRY_PENDING; requested reduce-only closure is EXIT_PENDING; actual quantity is retained in both.
- Milestone 6B follow-up CI: https://github.com/novacorestudios/Pvp-24/actions/runs/35437761623 — SUCCESS.
- Milestone 7 remote commit: e785fac3164989a3d96fee80aa73dec8edf00f74.
- Milestone 7 CI: https://github.com/novacorestudios/Pvp-24/actions/runs/35438716400 — SUCCESS.
- Milestone 8A remote commit: e9a777c9d52c38839658c674c1559eb064754a28.
- Milestone 8A CI: https://github.com/novacorestudios/Pvp-24/actions/runs/35439083883 — SUCCESS.
- Milestone 8B remote commit: f4277cb239650ca73154cb672b22d552c4f3b2b9.
- Milestone 8B CI: https://github.com/novacorestudios/Pvp-24/actions/runs/35439373000 — SUCCESS.
- Milestone 8C remote commit: 7a0c7624069eefb566e9eb088de68411b1ab61cd.
- Milestone 8C CI: https://github.com/novacorestudios/Pvp-24/actions/runs/35439587777 — SUCCESS.
- Milestone 8D CI: https://github.com/novacorestudios/Pvp-24/actions/runs/35439896937 — SUCCESS.
- Milestone 8E: 2791d54dddc336385081c3bd360b90c1df118825; CI https://github.com/novacorestudios/Pvp-24/actions/runs/35453636123 — SUCCESS.
- Milestone 9A: e69dc6cb1ea2913fdde327570520dfdc42cc0e63; CI https://github.com/novacorestudios/Pvp-24/actions/runs/35453952616 — SUCCESS.
- Milestone 9B: fa09a79a50d4ac8ec84ff280172cace4f949c04f; CI https://github.com/novacorestudios/Pvp-24/actions/runs/35454387409 — SUCCESS.
- Milestone 9C: 822a208c3ac6e5b88fac6a8ae3643520b8f93c98; CI https://github.com/novacorestudios/Pvp-24/actions/runs/35454708288 — SUCCESS.
- Milestone 9D: f50003585ca9fbcdecdb6f4b9ada205884e2b053; CI https://github.com/novacorestudios/Pvp-24/actions/runs/35455066973 — SUCCESS.
- Milestone 9E: 6f3ae916f2f53bfdc4fc8b93fdde8a9f5442a2c1; CI https://github.com/novacorestudios/Pvp-24/actions/runs/35469054180 — SUCCESS.
- Milestone 9F: af65c2cf2d79a4acf747ed9d159e17fd3f34f2e8; CI https://github.com/novacorestudios/Pvp-24/actions/runs/35469509614 — SUCCESS.
- Milestone 10A: f93c4e52002878f1fc9c53d5d00ebb15438ffbd1; CI https://github.com/novacorestudios/Pvp-24/actions/runs/35469989993 — SUCCESS.
- Milestone 10B: 0f0785c74abe84c87bf14191329d0c5e38244b6b; CI https://github.com/novacorestudios/Pvp-24/actions/runs/35489760438 — SUCCESS.
- Milestone 10C: 965c4bd3ec2ce87844f6fa365c33f5b33b20c19d; CI https://github.com/novacorestudios/Pvp-24/actions/runs/35490066066 — SUCCESS.
- Next: publish/verify Milestone 10D CI; build a concrete durable PAPER backend that honors Decimal IOC/reduce-only/LAST, stores orders and execution evidence before returning, and is hosted solely by PVB24Executor. Wire feed/event processing and validate actual process parity. Keep operational_ready=false until qualification. Historical ingestion/general historical driver, stress/acceptance and paper readiness remain incomplete.
- Code: immutable Fill/Side types, precision-34 Decimal helpers, canonical IDs, SQLite WAL events/snapshots/write-ahead intents, fail-closed paper guard. Causal Timing/Candle/Mark/rule/security models, as-of revision selection, 30-day gap warmup, deterministic historical Top-20 and stale-universe grace implemented. Streaming Wilder ATR, channel/RVOL, exact long/short transitions, restartable indicator checkpoints, cooldown/status gates and timed simultaneous batch ranking implemented. Risk foundations now include rounded protective-stop costs, separate arrival shortfall gate, causal funding reserve with explicit coverage, immutable open/pending portfolio reservations and proportional confirmed-exit release. Descending quantity-step sizing, 1..5x minimum feasible leverage, isolated tier-consistent liquidation reconstruction, reduce-only post-fill action interface and transactional reservation+ENTRY intent are implemented. Execution market models now include sequence-consistent L2, consumed-depth replay, strict IOC caps and gates, partial sweep previews, and labelled preliminary OHLC proxies. Confirmed-fill protection lifecycle and transactional evidence/state/action-intent persistence now exist. Open-position reconciliation is now implemented; execution adapter and integrated backtest remain unimplemented. Exchange liquidation validation is still absent; actual post-fill collateral must come from the adapter, not a hypothetical newly opened smaller position.
- Data: none acquired; OHLCV/Mark/funding/historical rules/security-master/L2 coverage remains unassessed. No backtest evidence, PRELIMINARY or VERIFIED.
- PAPER: NOT READY. LIVE: DISABLED. No orders sent.
- Original source and baseline config hashes unchanged. See config/manifest.json.
- Deviation: existing repository display capitalization Pvp-24 retained. No alpha changes.
- Artifacts: local artifacts/freqtrade-smoke.log and install logs; successful commands in docs/REPRODUCE.md.
- No automated background restart is configured or claimed.

Milestone 3 initial CI passed: https://github.com/novacorestudios/Pvp-24/actions/runs/35423805823. Review follow-up: unknown IOC/stop support now defaults to false; expired rules are rejected at their effective_to boundary.

## Current publication and credit checkpoint

The user requested frequent GitHub checkpoints and a status update before credit exhaustion where detectable. Remaining credits are not exposed to this process. Publish tested milestones promptly; if any usage-limit warning appears, preserve changes and report the exact remote HEAD/next action without promising background reactivation.

## Solver limitations carried into execution work

Exact descending step search preserves largest-feasible semantics even across rounding/tier discontinuities. It is not performance-qualified for extremely fine quantity increments; dispatch deadlines must still reject late results. No real Binance liquidation fixture has been acquired: all new tests are synthetic mathematics/concurrency tests, not exchange validation. The post-fill action wrapper requires an adapter-backed residual-position solver with confirmed fills, unchanged original stop, and known collateral/reduction costs. Do not pass entry sizing as if closing automatically released or restored collateral.

Milestone 7: shared close-based exit engine implements first-three-close failure, sixth-close weak follow-through, 2R trailing activation, 3-current-ATR close-extreme trailing, conservative tick tightening, no widening, separate proposal/acknowledged-effective timestamps, 72h actual-fill timer and restart checkpoints. Equal-time/pre-fill closes and all high/low extrema are excluded from close-based MFE. Missing eligible candles require causal reconciliation; the independent 72h timer still runs. This is not yet a fully wired backtest or paper adapter.

Milestone 8A: fill/fee/funding ledger with explicit position ownership, actual remaining cost basis, late-arrival as-of views, source-confirmed funding eligibility, liquidation visibility and transactional checkpoint persistence. Mark-only equity rejects missing/stale/conflicting inputs. Minute risk controls implement -4% daily pause, 10% reduced risk until original peak recovery, and sticky 15% hard pause; safety pauses survive daily reset. Missing midnight equity is not replaced with a later value.

Mark freshness has no invented numerical default. A source-specific maximum age must be frozen and recorded in the future run manifest before any acceptance replay. Non-USDT fee ingestion must supply a documented causal USDT conversion in the adapter; current Fill.fee is explicitly USDT. Production entry gating must combine this risk overlay with freshness/reconciliation/protection; these pieces are not yet an operational paper system.

Milestone 8B: AccountCoordinator now journals each confirmed fill, ledger update, protective action intent and account-entry reconciliation pause in one transaction. Funding also invalidates prior account-risk reconciliation. All pending reservations remain locked until actual outcomes are known. A flat account releases reservations only when cash matches, every owned entry is proven terminal and quantities are zero. Reconciliation cannot be backdated; safety pauses remain latched. New Reservations calls fail closed while this account gate is unresolved. Open-position collateral/risk reconciliation is the immediate remaining integration gate; flat reconciliation cannot bypass it.

Milestone 8C: liquidation-only repair now evaluates residual positions using actual isolated collateral after fees/settled funding, original entry VWAP and fixed initial stop. Each hypothetical reduction must provide a causal execution/fee/collateral-release projection. No added collateral or fresh-entry margin is assumed. Unknown/unverified economics request a full reduce-only close; otherwise descending step search returns the largest quantity restoring 3R. Tests demonstrate that proportional collateral release can make size reduction unable to repair the buffer. This helper does not yet enforce every portfolio post-fill constraint or establish VERIFIED exchange behavior.

Milestone 8D: AccountRiskService freezes an explicit source-specific Mark freshness policy before observing trading cashflows, journals minute risk samples, cancels pending entries on new daily/hard pauses, and emits reduce-only close intents for a hard pause. Outstanding unknown closes are not resubmitted; newly confirmed uncovered quantity receives an additional bounded close request. Reservations and ENTRY dispatch claims consult durable account/equity gates when initialized; protection and exits remain dispatchable. Operational adapter must require these streams and check sample freshness and the original signal deadline at dispatch. No numerical production Mark-age policy has been invented or frozen.


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
