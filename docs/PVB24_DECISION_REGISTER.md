# PVB-24 decision register

Frozen before any performance run. Config SHA256: `6d267edbcde56081012bc7b93d46f2c7f345aceb0e3bc769095ba53ef00b5be7`.

The complete decision text is hash-covered in config/pvb24_v1.json. The hash is not embedded in itself. Derived random seed is computed from that hash, avoiding circular hashing.

## UD-01 — Statistical definitions

- rationale: Pre-authorized before performance observation; do not select by PnL.
- source_option: Master section 6; frozen source section 110 UD-01
- owner: Project implementation directive
- date: 2026-09-19
- impact: Statistical definitions
- alpha_semantics_changed: False
- config_hash: 6d267edbcde56081012bc7b93d46f2c7f345aceb0e3bc769095ba53ef00b5be7

- even-count median = arithmetic mean of the two middle sorted values.
- standard deviation for descriptive rolling volatility = population std, ddof=0.
- 1m return used by preliminary sigma = log(close_t / close_t-1).
- quantiles used in strategy/risk rules = nearest-rank.
- percentile_95 = nearest-rank.
- Sortino downside deviation = sqrt(mean(min(daily_return, 0)^2)) over ALL
  valid daily observations, including zero contribution from non-negative days.
- Bootstrap confidence interval = percentile CI.

## UD-02 — ATR origin and gaps

- rationale: Pre-authorized before performance observation; do not select by PnL.
- source_option: Master section 6; frozen source section 110 UD-02
- owner: Project implementation directive
- date: 2026-09-19
- impact: ATR origin and gaps
- alpha_semantics_changed: False
- config_hash: 6d267edbcde56081012bc7b93d46f2c7f345aceb0e3bc769095ba53ef00b5be7

- Wilder ATR(24) is seeded from the earliest 24 VALID true ranges in the causal
  history available before the tested interval.
- Persist ATR checkpoints so restart does not re-seed differently.
- A missing required 1h candle is a data gap, not a zero-volume candle.
- After a required 1h data gap, that symbol cannot create new signals until it
  again has a complete 30-day warmup window.
- A zero-volume candle is valid only if the upstream venue/archive explicitly
  contains it as a legitimate candle.

## UD-03 — Universe security master / stale list

- rationale: Pre-authorized before performance observation; do not select by PnL.
- source_option: Master section 6; frozen source section 110 UD-03
- owner: Project implementation directive
- date: 2026-09-19
- impact: Universe security master / stale list
- alpha_semantics_changed: False
- config_hash: 6d267edbcde56081012bc7b93d46f2c7f345aceb0e3bc769095ba53ef00b5be7

- Universe refresh is scheduled at 00:05 UTC.
- stale-universe grace ends at 01:05 UTC.
- Historical eligibility must come from a versioned security-master source.
- Prefer official Binance historical metadata/archives when available.
- Store symbol changes, listing start, delisting, contract-size changes, and
  source revision IDs.
- If exact historical metadata is unavailable, label that period PRELIMINARY
  and disclose survivorship/metadata uncertainty. Do not fabricate.
- No new entry is allowed after stale grace expires without a valid universe.

## UD-04 — Temporal availability / batch

- rationale: Pre-authorized before performance observation; do not select by PnL.
- source_option: Master section 6; frozen source section 110 UD-04
- owner: Project implementation directive
- date: 2026-09-19
- impact: Temporal availability / batch
- alpha_semantics_changed: False
- config_hash: 6d267edbcde56081012bc7b93d46f2c7f345aceb0e3bc769095ba53ef00b5be7

- For each hourly signal batch, wait until all required inputs for a symbol are
  available OR the 30-second signal-data deadline is reached.
- At the deadline, reject only symbols whose required inputs remain unavailable.
- Rank all complete simultaneous signals deterministically.
- Data is timely when available_at <= signal_time + 30s.
- An entry may be sent only when order_sent_at <= signal_time + 90s.
- A signal after the deadline is expired.
- Live/Paper latency uses measured timestamps.
- Preliminary historical mode uses the specification's fixed +2s availability.
- Store exchange event time, local receive time, and monotonic processing time.
- Never backdate decision_time.

## UD-05 — IOC cap / L2

- rationale: Pre-authorized before performance observation; do not select by PnL.
- source_option: Master section 6; frozen source section 110 UD-05
- owner: Project implementation directive
- date: 2026-09-19
- impact: IOC cap / L2
- alpha_semantics_changed: False
- config_hash: 6d267edbcde56081012bc7b93d46f2c7f345aceb0e3bc769095ba53ef00b5be7

- Require sequence-consistent L2 when operating in VERIFIED execution mode.
- Use both event-time and receive-time age; the book is stale if EITHER exceeds
  the configured 500ms gate after clock normalization.
- Haircut stress removes visible quantity proportionally from each level.
- In replay, consumed visible depth is not reusable until a later book update
  replenishes it.
- The marketable IOC limit price may never permit a fill outside the strictest
  of the configured channel-distance, signal-close-deviation, and depth-impact
  constraints.
- LONG limit rounding must never widen the worst acceptable price: round the
  final cap DOWN to tick.
- SHORT limit rounding must never widen the worst acceptable price: round the
  final floor UP to tick.
- If a valid marketable price cannot be expressed after rounding, reject.

## UD-06 — IDs / durable state

- rationale: Pre-authorized before performance observation; do not select by PnL.
- source_option: Master section 6; frozen source section 110 UD-06
- owner: Project implementation directive
- date: 2026-09-19
- impact: IDs / durable state
- alpha_semantics_changed: False
- config_hash: 6d267edbcde56081012bc7b93d46f2c7f345aceb0e3bc769095ba53ef00b5be7

- Canonical identity strings are UTF-8 with stable field order.
- SHA-256 is the canonical digest algorithm.
- Store the full canonical identity and full digest.
- Exchange client_order_id uses a deterministic shortened representation that
  obeys the pinned exchange limit; the full mapping is persisted.
- Use a transactional event journal with write-ahead order intent.
- SQLite WAL is acceptable for local research/paper unless the implementation
  proves a stronger store is necessary.
- Never retry an unknown order outcome until querying by client_order_id.

## UD-07 — SPEC_CONFLICT-02 / IOC unfilled cooldown

- rationale: Pre-authorized before performance observation; do not select by PnL.
- source_option: Master section 6; frozen source section 110 UD-07
- owner: Project implementation directive
- date: 2026-09-19
- impact: SPEC_CONFLICT-02 / IOC unfilled cooldown
- alpha_semantics_changed: False
- config_hash: 6d267edbcde56081012bc7b93d46f2c7f345aceb0e3bc769095ba53ef00b5be7

- An IOC with ZERO fill consumes that signal_id.
- It returns the symbol to READY, NOT the six-hour post-position cooldown.
- A new trade still requires a new false-to-true breakout transition.
- The six-hour cooldown starts only after a real position reaches full_exit_time.

## UD-08 — Protection / exits / rounding

- rationale: Pre-authorized before performance observation; do not select by PnL.
- source_option: Master section 6; frozen source section 110 UD-08
- owner: Project implementation directive
- date: 2026-09-19
- impact: Protection / exits / rounding
- alpha_semantics_changed: False
- config_hash: 6d267edbcde56081012bc7b93d46f2c7f345aceb0e3bc769095ba53ef00b5be7

- Every confirmed fill must become protected as soon as operationally possible.
- Use idempotent retries and reconciliation for stop placement.
- If protection cannot be confirmed promptly, reduce-only close the affected
  quantity and enter a safety pause.
- Local mandatory exits use reduce-only market behavior in the reference model,
  with taker fees and adverse execution modeled.
- Trailing stop tightening:
  LONG -> round UP to tick if that tightens protection and remains a valid trigger.
  SHORT -> round DOWN to tick if that tightens protection and remains valid.
- Never widen an effective stop.
- For entry partial fills, protect the confirmed cumulative quantity.
- After IOC reaches terminal state, freeze final entry_vwap, final initial_stop,
  and initial_price_risk.
- During cancel/fill races, exchange-confirmed fills are authoritative.
- Reduce-only semantics must prevent position reversal.

## UD-09 — Risk solver / post-fill breach

- rationale: Pre-authorized before performance observation; do not select by PnL.
- source_option: Master section 6; frozen source section 110 UD-09
- owner: Project implementation directive
- date: 2026-09-19
- impact: Risk solver / post-fill breach
- alpha_semantics_changed: False
- config_hash: 6d267edbcde56081012bc7b93d46f2c7f345aceb0e3bc769095ba53ef00b5be7

- Use deterministic monotonic search over quantity-step units.
- Recompute expected execution price, costs, margin, and liquidation in each
  sizing iteration.
- Maximum outer sizing iterations = 5, as required by the source spec.
- Converged = same rounded quantity on two consecutive iterations.
- Pending notional is valued at expected entry.
- Open-position gross notional is valued at current Mark.
- Never round quantity upward to satisfy minimums.
- If a post-fill breach can be corrected by a reduce-only reduction, reduce to
  the largest compliant quantity.
- If a compliant quantity cannot be determined safely, close the position.
- After an actually confirmed partial exit, reserved initial risk may scale
  proportionally to remaining quantity; tighter stop alone never releases risk.

## UD-10 — Liquidation / gap

- rationale: Pre-authorized before performance observation; do not select by PnL.
- source_option: Master section 6; frozen source section 110 UD-10
- owner: Project implementation directive
- date: 2026-09-19
- impact: Liquidation / gap
- alpha_semantics_changed: False
- config_hash: 6d267edbcde56081012bc7b93d46f2c7f345aceb0e3bc769095ba53ef00b5be7

- LIVE is prohibited, but the model must still be implemented.
- Use exchange-provided liquidation information where available.
- Implement a Binance USD-M liquidation adapter based on the pinned official
  rules and maintenance tiers.
- Validate the calculator against exchange-provided values in safe/non-live
  contexts before calling it VERIFIED.
- For historical periods lacking historical maintenance tiers, label liquidation
  reconstruction UNVERIFIED; never use today's tiers as exact history.
- The 3R liquidation buffer is mandatory.
- If an open position's verified liquidation buffer deteriorates below 3R,
  reduce position size to restore the buffer if possible; otherwise close.
- Gap 1R and 2R scenarios are STRESS REPORTS, not extra Alpha entry filters.
- Any actual modeled liquidation remains visible in reports.

## UD-11 — SPEC_CONFLICT-03 / costs / funding

- rationale: Pre-authorized before performance observation; do not select by PnL.
- source_option: Master section 6; frozen source section 110 UD-11
- owner: Project implementation directive
- date: 2026-09-19
- impact: SPEC_CONFLICT-03 / costs / funding
- alpha_semantics_changed: False
- config_hash: 6d267edbcde56081012bc7b93d46f2c7f345aceb0e3bc769095ba53ef00b5be7

- For sizing, do NOT double-count entry price impact that is already embedded in
  expected_entry.
- For the cost-to-risk gate, define an explicit arrival-price execution shortfall:
  LONG reference = best_ask at decision.
  SHORT reference = best_bid at decision.
- estimated_total_cost for the gate includes:
  entry execution shortfall vs arrival side price
  + entry fee
  + expected stop-exit fee
  + stop-exit slippage reserve
  + adverse funding reserve.
- entry execution shortfall is a REPORT/GATE component only and is NOT deducted
  a second time from realized PnL.
- Realized PnL uses actual fills, actual fees, and actual funding exactly once.
- If an account-specific historical fee schedule is unavailable, preliminary
  research may use 0.0005 taker fee per side, explicitly labeled as an assumption.
- Missing funding history is never replaced by zero.
- VERIFIED acceptance requires adequate funding coverage for held positions.
- Non-USDT fee assets, if ever encountered, are converted using a causal price
  available at the fee event time and the conversion source is logged.

## UD-12 — Equal-time ordering

- rationale: Pre-authorized before performance observation; do not select by PnL.
- source_option: Master section 6; frozen source section 110 UD-12
- owner: Project implementation directive
- date: 2026-09-19
- impact: Equal-time ordering
- alpha_semantics_changed: False
- config_hash: 6d267edbcde56081012bc7b93d46f2c7f345aceb0e3bc769095ba53ef00b5be7

- Use exchange sequence numbers when available.
- Otherwise use a deterministic conservative order for same-timestamp ambiguity:
  1) confirmed liquidation / forced venue event;
  2) confirmed fills of already-live protective orders;
  3) confirmed fills of other already-live reduce-only exits;
  4) funding settlement for a position proven eligible at that boundary;
  5) account/equity risk-state update;
  6) candle-close early-failure / weak-followthrough / time decisions;
  7) trailing-stop recalculation and replacement;
  8) new entry decisions.
- A candle with interval_end == first_fill_time is NOT an eligible post-entry close.
- Do not use high/low movement that occurred before first_fill_time.
- If data are insufficient to order a liquidation vs stop, apply the adverse
  assumption and increment ambiguous_event_count.

## UD-13 — Historical coverage / delisting

- rationale: Pre-authorized before performance observation; do not select by PnL.
- source_option: Master section 6; frozen source section 110 UD-13
- owner: Project implementation directive
- date: 2026-09-19
- impact: Historical coverage / delisting
- alpha_semantics_changed: False
- config_hash: 6d267edbcde56081012bc7b93d46f2c7f345aceb0e3bc769095ba53ef00b5be7

- Prefer official Binance archives and versioned exchange metadata.
- Build an explicit coverage report by symbol/date/source.
- Do not silently drop periods with missing rules.
- When a delisting announcement timestamp is causally available, block new entries
  from that symbol immediately.
- Existing positions are managed normally until an orderly close is possible;
  the exact close event and reason are logged.
- If only forced settlement is known historically, record the forced settlement
  rather than inventing an earlier announcement.

## UD-14 — SPEC_CONFLICT-01 / preliminary execution

- rationale: Pre-authorized before performance observation; do not select by PnL.
- source_option: Master section 6; frozen source section 110 UD-14
- owner: Project implementation directive
- date: 2026-09-19
- impact: SPEC_CONFLICT-01 / preliminary execution
- alpha_semantics_changed: False
- config_hash: 6d267edbcde56081012bc7b93d46f2c7f345aceb0e3bc769095ba53ef00b5be7

- Two execution-quality modes exist:
  PRELIMINARY and VERIFIED.
- PRELIMINARY may use 1m OHLCV plus the frozen proxy/slippage model.
- PRELIMINARY MUST label book-age/spread/depth/partial-fill fidelity UNVERIFIED
  rather than silently passing those gates.
- VERIFIED requires the necessary Quotes/L2/Mark/contract-rule data.
- A PRELIMINARY run may reject the hypothesis, but it cannot by itself establish
  production execution fidelity.
- In OHLC-only intrabar ambiguity, use the adverse/conservative event order.
- If both protective stop and liquidation are possible in the same unresolved
  bar, count liquidation first for sensitivity and record the ambiguity.
- Gap-through-stop exits use the first causally available executable price, not
  the stop trigger price.
- PRELIMINARY does not claim queue position or realistic partial fills.

## UD-15 — Physical schemas / precision

- rationale: Pre-authorized before performance observation; do not select by PnL.
- source_option: Master section 6; frozen source section 110 UD-15
- owner: Project implementation directive
- date: 2026-09-19
- impact: Physical schemas / precision
- alpha_semantics_changed: False
- config_hash: 6d267edbcde56081012bc7b93d46f2c7f345aceb0e3bc769095ba53ef00b5be7

- Internal arithmetic: Python Decimal, context precision 34.
- Never use binary float for exchange price, quantity, fees, cash, margin, or PnL.
- CSV:
  UTF-8, comma delimiter, RFC-compatible quoting, ISO-8601 UTC timestamps,
  Decimal values serialized as exact strings, literal NULL for missing values.
- Parquet:
  ZSTD compression, timestamp[us, UTC], DECIMAL(38,18) where compatible.
- schema_version = "1.0.0".
- Canonical JSON for hashes: UTF-8, sorted keys, no insignificant whitespace,
  explicit nulls, Decimal serialized as canonical decimal string.
- Hash = SHA-256.

## UD-16 — Environment / reproducibility

- rationale: Pre-authorized before performance observation; do not select by PnL.
- source_option: Master section 6; frozen source section 110 UD-16
- owner: Project implementation directive
- date: 2026-09-19
- impact: Environment / reproducibility
- alpha_semantics_changed: False
- config_hash: 6d267edbcde56081012bc7b93d46f2c7f345aceb0e3bc769095ba53ef00b5be7

- Repository = pvp-24.
- Working branch = build/pvb24-v1.
- Architecture = external event-driven reference engine + Freqtrade execution adapter.
- Freqtrade = official latest stable non-prerelease at bootstrap, then exact tag/SHA pin.
- Python = a version explicitly supported by the pinned Freqtrade release.
- Hashes = SHA-256 over canonical manifests.
- Single order authority in PAPER = Freqtrade adapter/executor.
- Reference engine never sends exchange orders directly.
- Exact CLI commands are created only after they have been successfully executed.
- Failed commands are recorded during development but not presented as successful
  reproduction steps.

## UD-17 — Equity / drawdown / resume

- rationale: Pre-authorized before performance observation; do not select by PnL.
- source_option: Master section 6; frozen source section 110 UD-17
- owner: Project implementation directive
- date: 2026-09-19
- impact: Equity / drawdown / resume
- alpha_semantics_changed: False
- config_hash: 6d267edbcde56081012bc7b93d46f2c7f345aceb0e3bc769095ba53ef00b5be7

- Backtest and paper use a dedicated strategy virtual ledger.
- Research runs have no external deposits/withdrawals after start.
- Future shared-account LIVE allocation is outside current scope.
- Equity sample grid = minute boundaries using latest causally available Mark.
- If Mark is stale or missing, pause new entries; never silently substitute Last
  for official equity/liquidation accounting.
- Reduced-risk state remembers the pre-drawdown peak that caused reduction.
- Return to 1% new-entry risk only after equity recovers that peak.
- 15% hard drawdown pause requires explicit operational review; daily reset cannot clear it.
- Global PAUSED is an overlay; symbol OPEN/TRAILING states remain active and protected.

## UD-18 — Validation governance

- rationale: Pre-authorized before performance observation; do not select by PnL.
- source_option: Master section 6; frozen source section 110 UD-18
- owner: Project implementation directive
- date: 2026-09-19
- impact: Validation governance
- alpha_semantics_changed: False
- config_hash: 6d267edbcde56081012bc7b93d46f2c7f345aceb0e3bc769095ba53ef00b5be7

- Before any Final Test run, commit:
  docs/FINAL_TEST_FREEZE.md
  containing code SHA, config hash, data manifest hash, and a declaration that
  Development/Validation work is frozen.
- Reference-account acceptance run = 1000 USDT initial equity.
- Capacity/sensitivity runs = 200 USDT and 10000 USDT using identical Alpha rules.
- Do not choose the best account size after results.
- Final Test sample gates (300 OOS trades, >=100 each direction, >=52 full weeks)
  apply to the reference acceptance run.
- Walk-forward uses continuous account state; no quarterly reset.
- Positions may carry across evaluation-window boundaries.
- If Final Test data were previously used to choose PVB-24 rules, mark it
  RETROSPECTIVE and create a future holdout plan; do not call it untouched.

## UD-19 — Statistical / stress protocol

- rationale: Pre-authorized before performance observation; do not select by PnL.
- source_option: Master section 6; frozen source section 110 UD-19
- owner: Project implementation directive
- date: 2026-09-19
- impact: Statistical / stress protocol
- alpha_semantics_changed: False
- config_hash: 6d267edbcde56081012bc7b93d46f2c7f345aceb0e3bc769095ba53ef00b5be7

- Portfolio-level moving-block bootstrap.
- Base block length = 7 days.
- Sensitivity block lengths = 3 and 14 days.
- Resamples = 5000.
- CI = 95% percentile interval.
- Bootstrap/random stress seed is derived deterministically from config_hash,
  not selected after observing returns.
- Fees-only stress = 2x fee rates, other execution assumptions unchanged.
- Outage stress schedules are generated from the precommitted deterministic seed
  before evaluating PnL.
- Report both:
  a) arithmetic removal of the best five closed trades for contribution sensitivity;
  b) optional full replay with those signal_ids disabled, explicitly noting that
     portfolio allocation can change.
- Concentration and "system stopped most of the period" are diagnostic flags unless
  a numeric rejection threshold was already frozen before Final Test.
- Never invent a late threshold after seeing Final Test.

## UD-20 — Diagnostic sampling

- rationale: Pre-authorized before performance observation; do not select by PnL.
- source_option: Master section 6; frozen source section 110 UD-20
- owner: Project implementation directive
- date: 2026-09-19
- impact: Diagnostic sampling
- alpha_semantics_changed: False
- config_hash: 6d267edbcde56081012bc7b93d46f2c7f345aceb0e3bc769095ba53ef00b5be7

- BTC regime reference = BTCUSDT.
- Snapshot frequency = daily at 00:00 UTC using the latest completed data available then.
- 30-day BTC return uses causal completed daily boundary values.
- Realized volatility uses 1h log returns:
  annualized_volatility = std(log_returns_1h, ddof=0) * sqrt(24 * 365)
- Volatility percentile reference = previous 365 completed days, current day excluded.
- When 365 days are unavailable, regime volatility label = UNCLASSIFIED.
- Liquidity diagnostics use causal prior 30-day median quote volume.
- Cost diagnostics use realized execution-shortfall buckets only for reporting,
  never for signal generation.
