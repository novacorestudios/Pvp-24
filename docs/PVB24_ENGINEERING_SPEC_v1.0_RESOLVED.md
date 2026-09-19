# PVB-24 v1.0 resolved implementation profile

Source SHA256: `098a3ca390bce81d506bdec011fc3a936ecbb793f46c2f117f337998bfc1c5d8`
Config SHA256: `6d267edbcde56081012bc7b93d46f2c7f345aceb0e3bc769095ba53ef00b5be7`

Frozen profile IMP-2026-09-19-A. No performance data have been inspected.

The source is included below unchanged. Its OPEN/READY_FOR_IMPLEMENTATION status is historical source text. The following authorized implementation decisions resolve the enumerated choices. Missing operational detail or exchange evidence remains a readiness blocker; this document does not claim the implementation is complete.

## Resolutions

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

## Original source

PVB-24 — Participation-Validated Breakout
Engineering Specification
Version: 1.0
Status: Research Strategy

DOCUMENT AUTHORITY AND READING RULES
هذا الملف يجمع المواصفة المعتمدة في المحادثة السابقة، ويحوّل معادلاتها إلى ASCII، ويلتزم بطلب PVB24_ENGINEERING_SPEC_REQUEST.txt المرفق. ليس تنفيذًا للبوت ولا تقرير اختبار. لا توجد نتائج ربحية أو تعبئات أو أوامر تشغيل مزعومة.
حالة النسخة البحثية لا تعني اكتمال قرارات التنفيذ. القيم غير المحسومة تحمل معرف UD وترد خياراتها حصريًا في القسم 110. التعارضات تحمل SPEC_CONFLICT ولا يحلها هذا الملف بصمت. أي اسم دالة داخل معادلة هو تعريف مواصفة، وليس استدعاء API جاهزًا.
النسخة الأساسية تعتمد اختراق السعر والحجم فقط. لا تدخل OI أو Taker أو EMA أو RSI أو Compression في الإشارة. مصدر الأفضلية المفترض هو استمرار إعادة التسعير والتدفقات بعد اختراق تدعمه مشاركة تداول أعلى، وليس إثباتًا سببيًا لهوية المتداولين. اختبار هذه الفرضية وقابلية تكذيبها يسبقان أي تشغيل حقيقي.
كل الأرقام إعدادات بحثية أولية معتمدة من النص السابق، وليست نتائج تحسين. هدف مضاعفة الحساب خلال أسبوع مقياس تقرير فقط؛ لا يغير الإشارات أو المخاطر. لا Martingale، ولا تعزيز، ولا رفع مخاطرة بعد خسارة، ولا فرض صفقات.

VARIABLE AND UNIT CONVENTIONS
price: USDT لكل وحدة من الأصل الأساسي.
quantity: وحدات الأصل الأساسي؛ تحويل وحدات العقود مسؤولية Adapter موثق.
USDT: قيمة نقدية أو اسمية أو تكلفة.
fraction: عدد عشري بلا وحدة؛ النسبة المئوية تحول إلى fraction قبل الحساب.
boolean: true أو false؛ unknown لا يعامل كـ false.
seconds / milliseconds: مدد، مع طوابع زمنية UTC؛ دقة تخزين الطابع UD-15.
index: مؤشر ترتيب شمعة، لا وقت وصولها.
all / any / max / min / sum / abs / sqrt / floor / ceil / median: وظائف رياضية بأسماء ASCII.
NaN وNull والقيم المفقودة ليست صفرًا. تستخدم حسابات Decimal للأسعار والكميات والأموال. دقة Decimal وتخزينه UD-15.

1. Strategy Identity
الاسم PVB-24، التوسعة Participation-Validated Breakout، الإصدار 1.0، والحالة Research Strategy. المرشح اختبار أول لفرضية واحدة، وليس أقوى استراتيجية مثبتة. وحدات Signal Engine وRisk Engine وExecution Engine وAccounting وResearch Reporting منفصلة. أول وضع بناء وتشغيل هو Paper. لا تفويض بتداول حقيقي في هذا الملف.
لا تستبدل استراتيجية قائمة أو مرجعًا مجمدًا عند دمجه في مشروع. تسجيل code_sha وconfig_hash وdata_hash إلزامي.

2. Market Type
السوق USDT Linear Perpetual فقط. الأرباح والخسائر خطية بالنسبة لكمية الأصل وحركة السعر، والتسوية بـ USDT. لا عقود عكسية، ولا Spot، ولا Expiry Futures في النسخة. قيمة contract_size إن وجدت تحول إلى quantity قبل المعادلات.

3. Exchange Assumptions
المرجع Binance USD-M. يلزم Adapter للتحقق من حالة العقد، tick_size وquantity_step وmin_quantity وmin_notional والرسوم والهامش والصيانة والتصفية والتمويل وأنواع الأوامر ومراجع تفعيل الوقف.
لا تفترض أن قواعد المنصة الحالية كانت سارية تاريخيًا. لا تخلط Adapter بحثي مع API حي. توثيق إصدار المنصة والمكتبة وتاريخ صلاحية كل قاعدة إلزامي. حساب الاستراتيجية معزول محاسبيًا؛ طريقة تخصيص حساب مشترك UD-17.

4. Timezone
UTC لجميع الشموع والأيام والأسابيع والمؤقتات. لا توقيت صيفي محلي. يوم التداول يبدأ 00:00 UTC. لا تقرب وقت وصول البيانات إلى بداية الشمعة.

5. Position Mode
ONE_WAY. لا يملك النظام LONG وSHORT متزامنين على الرمز نفسه. أمر خروج لا يفتح اتجاهًا معاكسًا. المصدر النهائي للكمية هو حالة المنصة والتعبئات المتصالحة.

6. Margin Mode
ISOLATED. لا انتقال آلي إلى Cross. لا إضافة هامش بعد الخسارة مقررة في هذه النسخة. تحقق من نجاح ضبط الهامش قبل الإرسال. أثر رسوم وتمويل المركز على الهامش المعزول يعاد حسابه وفق Adapter.

7. Supported Directions
LONG وSHORT بقواعد متناظرة للإشارة والخروج. التناظر البرمجي لا يثبت تساوي الربحية أو التمويل أو مخاطر القفزات. لا تعديل منفصل لمعيار اتجاه بناء على نتيجة Final Test.

8. Universe Selection
عند 00:05 UTC يوميًا، اختر العقود النشطة وقت القرار، بعمر 90 يومًا على الأقل، وتاريخ كامل آخر 30 يومًا. استبعد العقود غير المرتبطة بأصول كريبتو والأصول المصممة لسعر ثابت وفق تصنيف متاح وقت القرار.
```text
universe_size = 20
universe_lookback_days = 30
minimum_median_daily_quote_volume = 50000000
median_daily_quote_volume = median(previous_30_completed_utc_daily_quote_volumes)
universe_sort_key = (-median_daily_quote_volume, symbol)
```
الوحدات: universe_size وlookback أعداد؛ daily_quote_volume وعتبته USDT؛ sort_key ترتيب لا وحدة له.
رتب المؤهلين بهذه المفاتيح وخذ أول 20؛ لا تخفض عتبة السيولة لملء القائمة. إذا تأخرت البيانات، تستعمل آخر قائمة صالحة لمدة ساعة كحد أقصى ثم تتوقف المداخل. نقطة بدء قياس الساعة UD-03. إذا لا توجد قائمة سابقة، لا دخول. خروج الرمز من القائمة لا يغلق مركزه.

9. Universe Historical Reconstruction
أعد بناء قائمة كل يوم من سجل العقود النشطة والأحجام والتصنيف المعروفة في ذلك اليوم. شمل المشطوبين وأحداث إعادة التسمية وتغيير contract_size وفق سجلاتها. لا تستعمل Top-20 الحالي أو معرفة الشطب اللاحقة. احفظ universe_id ومكوناتها وأسباب الاستبعاد وتوقيت الإتاحة ومدخلات الترتيب. مصدر سجل الرموز والتصنيف وتاريخ المراجعات UD-03 وUD-13. لا تحذف أيامًا خاسرة بسبب قصور البيانات دون كشفها في تقرير التغطية.

10. Listing Age Rules
```text
minimum_listing_age_days = 90
listing_age_seconds = decision_time - trading_start_time
listing_age_ok = listing_age_seconds >= 90 * 24 * 60 * 60
```
الوحدات: الطوابع UTC، الفرق seconds، العمر days، والنتيجة boolean.
trading_start_time وقت بدء تداول العقد نفسه، لا عمر مشروع العملة. بيانات بدء التداول وإعادة الإدراج UD-03. لا يستخدم تاريخ نهاية الأرشيف لاستنتاج أهلية قديمة.

11. Liquidity Filters
فلاتر السيولة المقررة: وسيط الحجم اليومي 50000000 USDT، السبريد الأقصى 0.0005 fraction، عمر الدفتر 500 milliseconds، أثر الدفتر 0.001 fraction، مشاركة الأمر 0.001 من حجم آخر 15 دقيقة مكتملة. المعادلات في الأقسام 36 إلى 39. هذه قيود تنفيذ وليست إشارات اتجاه.
لا تتوافر هذه المقاييس كلها من OHLCV. حدود الاختبار الأولي موثقة في SPEC_CONFLICT-01 والقسم 83.

12. Data Warmup
30 يومًا مكتملًا على الأقل لكل رمز قبل أول إشارة. تحتاج القناة السابقة 24 شمعة 1h لكل حالة، ومرجع الحجم 48 شمعة سابقة، وحالتي الاختراق الحالية والسابقة، وATR مسبقًا.
لا تولد إشارات أثناء التهيئة. بيانات missing مختلفة عن شمعة صحيحة بحجم صفر. معالجة الشموع المفقودة ونقطة تثبيت بذرة ATR UD-02. تهيئة التمويل والتصنيف السوقي منفصلة ولا تختصر إلى warmup السعر.

13. Timeframes
1h للإشارة والقناة وATR وRVOL وإغلاقات الخروج وTrailing. 1m للاختبار الأولي وEquity ولحساب آخر 15 دقيقة تنفيذ. Trades/Quotes/L2 للتنفيذ الدقيق عند توفرها. أيام UTC لحجم Universe وعوائد التقارير. لا إطار 3m أو 5m أو 15m أو 4h للإشارة الأساسية. نافذة 15 دقيقة هنا تجميع تنفيذ من بيانات مكتملة وليست إشارة مستقلة.

14. Candle Definitions
```text
candle_interval = [interval_start, interval_end)
signal_time = interval_end_of_signal_1h_candle
```
الوحدات: interval_start وinterval_end وsignal_time طوابع UTC. الفترة نصف مفتوحة. شمعة t آخر شمعة 1h مكتملة ومتاحة للقرار؛ t-1 تسبقها زمنيًا.
Open وHigh وLow وClose من أسعار Last، وquote_volume بـ USDT. لا تشارك شمعة الإشارة في قناة سابقة أو وسيط حجم سابق. حدود الوقت العددية ودقة الطابع UD-15. الشموع المعاد تجميعها يجب أن تتطابق مع تعريف المصدر، وتوثق مراجعاتها.

15. Channel Definition
```text
lookback_hours = 24
channel_high[t] = max(high[t-24], ..., high[t-1])
channel_low[t] = min(low[t-24], ..., low[t-1])
```
الوحدات: lookback_hours hours؛ high وlow وchannel_high وchannel_low price.
تعني النقاط المتتابعة كل الشموع المفهرسة ضمن المدى شاملًا الطرفين؛ لا تشمل t. حدود صفقة مفتوحة تثبت عند توليد إشارتها تحت entry_channel_high وentry_channel_low.

16. ATR Definition
Wilder ATR بفترة 24 على 1h، وليس SMA متحركًا لـ TR بعد التهيئة.
```text
atr_period = 24
true_range[t] = max(high[t] - low[t], abs(high[t] - close[t-1]), abs(low[t] - close[t-1]))
atr_seed = mean(first_24_valid_true_ranges)
atr[t] = (23 * atr[t-1] + true_range[t]) / 24
atr_previous[t] = atr[t-1]
```
الوحدات: atr_period عدد شموع 1h؛ true_range وatr وatr_previous price.
القناة ومعيار الاختراق والوقف يستخدمون atr_previous. Trailing يستخدم atr الحالي المكتمل. نقطة بداية first_24_valid_true_ranges ومعالجة أول close سابق UD-02؛ لا يعاد بذر ATR كل تشغيل بصمت.

17. Relative Volume Definition
```text
volume_lookback_bars = 48
current_quote_volume = quote_volume[t]
historical_volume_reference = median(quote_volume[t-48], ..., quote_volume[t-1])
rvol = current_quote_volume / historical_volume_reference
rvol_threshold = 1.5
```
الوحدات: volume_lookback_bars عدد شموع 1h؛ أحجام التداول USDT؛ rvol وrvol_threshold نسب بلا وحدة.
المرجع median، لا mean ولا SMA. إذا المرجع صفر أو المدخلات ناقصة، الإشارة غير صالحة. تعريف median للعدد الزوجي مذكور في UD-01 لأنه لم يحدد صراحة في مواصفة PVB-24 السابقة.

18. All Indicator Initialization Rules
يلزم تاريخ صالح لحساب حالة t-1 وحالة t كل واحدة بمدخلاتها. لا يعامل previous_breakout_state المجهول كـ false. تجميد atr_previous مع الإشارة إلزامي. rolling highs/lows لا تستخدم centered windows. median وتعريف std وquantile وبذرة ATR والتقريب العشري مدرجة في UD-01 وUD-02 وUD-15. لا يستورد المبرمج قيم defaults من مكتبة المؤشرات قبل حسمها. لا مؤشرات إضافية داخل النسخة.

19. LONG Conditions
```text
current_long_breakout_state = close[t] > channel_high[t] + 0.10 * atr_previous[t]
previous_long_breakout_state = close[t-1] > channel_high[t-1] + 0.10 * atr_previous[t-1]
new_long_breakout = current_long_breakout_state and not previous_long_breakout_state
long_signal = (
    symbol_in_active_universe
    and new_long_breakout
    and rvol >= 1.5
    and not symbol_has_position
    and not symbol_has_pending_entry
    and cooldown_finished
    and all_required_data_complete
    and all_required_data_available
)
```
الوحدات: الأسعار وATR price؛ 0.10 وrvol نسب؛ جميع الشروط وlong_signal boolean.
علامة الاختراق strict >، لا >=. الحجم يقبل المساواة. هذه إشارة وليست موافقة Risk Engine. لا شرط EMA أو OI أو Taker أو RSI أو Funding اتجاهي.

20. SHORT Conditions
```text
current_short_breakout_state = close[t] < channel_low[t] - 0.10 * atr_previous[t]
previous_short_breakout_state = close[t-1] < channel_low[t-1] - 0.10 * atr_previous[t-1]
new_short_breakout = current_short_breakout_state and not previous_short_breakout_state
short_signal = (
    symbol_in_active_universe
    and new_short_breakout
    and rvol >= 1.5
    and not symbol_has_position
    and not symbol_has_pending_entry
    and cooldown_finished
    and all_required_data_complete
    and all_required_data_available
)
```
الوحدات: الأسعار وATR price؛ 0.10 وrvol نسب؛ short_signal وباقي الشروط boolean.
علامة الاختراق strict <. لا تطارد إشارة فات شرط حجمها بينما بقيت حالة الاختراق true.

21. Breakout false-to-true transition logic
```text
channel_high[t-1] = max(high[t-25], ..., high[t-2])
channel_low[t-1] = min(low[t-25], ..., low[t-2])
atr_previous[t-1] = atr[t-2]
new_breakout = (current_breakout_state == true) and (previous_breakout_state == false)
```
الوحدات: حدود القناة وATR price؛ الحالات والنتيجة boolean.
الحالة السابقة تحسب بحدودها السابقة، لا بقناة t. RVOL وUniverse وموافقة المخاطر ليست جزءًا من تعريف breakout_state. لا تؤخر transition إلى ساعة لاحقة بسبب رفض المخاطر أو ضعف الحجم. فقدان الحالة السابقة يوقف الإشارة حتى تتوفر بياناتها.

22. Signal ID construction
المكونات المطلوبة: strategy_version وsymbol وdirection وsignal_time. جهة الحساب/التشغيل تدخل في client_order_id لمنع التداخل، ولا تحول إشارة واحدة إلى إشارتين بعد Restart.
```text
signal_identity_fields = (strategy_version, symbol, direction, signal_time)
```
الوحدات: نصوص وطابع UTC؛ الهوية tuple لا وحدة لها. طريقة Serialization وHash وطول المعرف واسم الرمز الموحد UD-06. لا يفترض Hash معين ضمن v1.0 دون حسمه. تحفظ الهوية قبل إرسال أي أمر.

23. Signal expiry
```text
signal_data_deadline = signal_time + 30_seconds
signal_order_deadline = signal_time + 90_seconds
```
الوحدات: الطوابع UTC والإضافات seconds. إذا لم تكتمل بيانات الإشارة ضمن 30 ثانية تلغى؛ إرسال الدخول بعد 90 ثانية ممنوع. شروط المساواة الدقيقة عند الموعد UD-04. لا يعاد تفعيل إشارة رفضت لانشغال المحفظة لاحقًا. انتهاء مهلة الدخول ليس إلغاء تلقائيًا لوقف حماية مركز قائم.

24. Signal invalidation
تبطل الإشارة بتأخر البيانات، خروج الرمز من القائمة، انتهاء المهلة، ارتداد السعر إلى الجانب غير الصالح، تجاوز مسافة الدخول، الانحراف عن signal_close، فشل السيولة أو المخاطر، أو وجود مركز/أمر متزامن. رفض حجم الإشارة لا يسمح باستعمال transition نفسه لاحقًا. التفريق بين استهلاك الإشارة وبدء Cooldown دون تعبئة UD-07 وSPEC_CONFLICT-02.

25. Simultaneous signal ranking
```text
sort_key_1 = -rvol
sort_key_2 = -median_daily_quote_volume
sort_key_3 = symbol
simultaneous_signal_sort_key = (sort_key_1, sort_key_2, sort_key_3)
```
الوحدات: rvol fraction-like ratio؛ الحجم USDT؛ symbol نص مرتب تصاعديًا. الترتيب تنازلي لأول معيارين، وأبجدي للثالث.
تجمع إشارات الساعة في دورة واحدة. الذرية في حجز الموارد إلزامية. لحظة إغلاق batch عند اختلاف أوقات وصول الرموز UD-04؛ لا تستخدم بيانات تصل بعد وقت قرار مدعى.

26. Decision time
```text
decision_time = max(available_at_of_each_required_signal_input)
```
الوحدات: طابع UTC. معناه أول وقت تكتمل فيه المعلومات اللازمة، وليس بالضرورة وقت بدء المعالج فعليًا. يسجل زمن بدء التقييم الفعلي منفصلًا إذا تأخر. اكتمال ترتيب batch جزء من المدخلات عند تطبيق ترتيب مشترك؛ تفصيله UD-04.
ميّز signal_time عن available_at وعن decision_time وعن order_sent_at وعن exchange_ack_at وعن fill_time. آخرها وقت تنفيذ المنصة، لا وقت استقبال تأكيدها.

27. available_at rules
السجل القياسي يحتوي event_time وinterval_start وinterval_end وavailable_at وreceived_at وsource وrevision_id. OHLCV وQuote volume لا يتيحان بيانات فترة قبل نهايتها. اللقطة اللحظية تحمل interval_start وinterval_end مساويين لـ event_time وrecord_type موضحًا كـ snapshot.
```text
causal_input_ok = available_at <= decision_time
completed_interval_ok = interval_end <= available_at
```
الوحدات: طوابع UTC ونتائج boolean؛ شرط completed_interval يطبق على السجلات الدورية، لا على تقدير معلن لفترة مستقبلية.
في الحي يتضمن available_at وصول السجل واكتماله والتحقق منه. تاريخيًا يلزم وقت وصول مسجل أو افتراض معلن؛ لا تزعم معرفة وصول لم يُحفظ. توثيق التعريف التفصيلي وتأخر التصحيح UD-04 وUD-13.
Funding النهائي محاسبة عند التسوية فقط. قواعد العقود بنسختها السارية. Universe يعتمد معلومات متاحة. مصادر OI وTaker وPremium وLiquidations ليست مدخلات أساسية؛ لا تعبئتها بصفر داخل Signal Engine.

28. Execution delay
التنفيذ بعد decision_time وإرسال الأمر ووصوله للمنصة. لا تعِد التنفيذ عند close الإشارة بأثر رجعي. الاختبار الأولي يفرض available_at بعد ثانيتين ويستخدم أول Open دقيقة يبدأ بعد القرار. تأخر الإرسال والشبكة والتأكيد في L2 والحي UD-04. سيناريوهات التأخير الإضافي 5 و30 و60 seconds في القسم 89. انتهاء المهلة تحت التأخير يلغي الإشارة.

29. Entry model
LONG يستهلك Ask وSHORT يستهلك Bid. احسب VWAP المتوقع للكمية من الدفتر السببي المتاح. يحدد سعر أمر IOC بحيث يحترم حدود الأثر والمطاردة. علاقة فحوص VWAP بسقف أسوأ تعبئة وتقريب السقف UD-05.
```text
expected_entry = sum(level_price * consumed_quantity_at_level) / sum(consumed_quantity_at_level)
entry_vwap = sum(fill_price * fill_quantity) / sum(fill_quantity)
```
الوحدات: level_price وfill_price وexpected_entry وentry_vwap price؛ consumed_quantity وfill_quantity quantity؛ جداءات السعر والكمية USDT.
expected_entry تقدير قبل الإرسال، entry_vwap نتيجة فعلية. لا تعتمد دفترًا لاحقًا لاختيار حجم كان يفترض اتخاذه سابقًا.

30. Order type
الدخول Marketable Limit IOC. لا Market غير محدود للدخول. الوقف Stop Market مخفض للمركز، مرجعه LAST/CONTRACT_PRICE. التفاصيل الدقيقة لنوع أمر الخروج الاختياري والطوارئ وسياسة إعادة المحاولة UD-08. Reject وعدم دعم مرجع الوقف يمنعان التداول على العقد. لا تعدل نوع الأمر تلقائيًا دون توثيق وموافقة على مواصفة منقحة.

31. IOC behavior
يقبل المنفذ الفوري، ويلغى الباقي حسب دلالة المنصة. عدم التعبئة يلغي الإشارة. لا إعادة محاولة لمطاردة سعر جديد على signal_id نفسه. استعادة نتيجة أمر غير مؤكدة تسبق قرار إرساله من جديد. مهلة تأكيد IOC وإجراءات Unknown status UD-06 وUD-08. يجب التمييز بين وصول Cancel وبين نهائيته؛ تعبئات متأخرة تظل صحيحة وتحتاج حماية.

32. Partial fill behavior
اعتمد الكمية المنفذة فقط، ألغ الباقي، وأعد حساب entry_vwap والوقف والهامش والمخاطرة. لا تكمل النقص لاحقًا. يجب حماية كل كمية مؤكدة. توقيت الحماية أثناء تدفق أجزاء IOC، وتعديل الوقف إذا تغير VWAP، وتعامل dust دون الحد الأدنى UD-08. لا تنشئ أهدافًا جزئية؛ partial fill تنفيذ غير كامل وليس partial take-profit.

33. Chasing limits
لا مطاردة كمية غير منفذة، ولا إعادة فتح الإشارة المستهلكة، ولا تحويل IOC المتبقي إلى Market. بقاء الاختراق وحدود مسافة القناة وانحراف signal_close كلها واجبة عند فحص التنفيذ. تمديد الصلاحية بسبب فحص بطيء ممنوع. مراجعة التجاوز المكتشف بعد التعبئة UD-05 وUD-09؛ لا يزعم النظام أن الفحص القبلي يضمن حدودًا فعلية مطلقة.

34. Maximum entry distance
```text
long_entry_distance = expected_entry - channel_high_at_signal
short_entry_distance = channel_low_at_signal - expected_entry
long_entry_distance_ok = (long_entry_distance > 0) and (long_entry_distance <= 1.0 * atr_previous_at_signal)
short_entry_distance_ok = (short_entry_distance > 0) and (short_entry_distance <= 1.0 * atr_previous_at_signal)
```
الوحدات: المسافات والأسعار وATR price؛ 1.0 معامل بلا وحدة؛ النتائج boolean. حدود القناة وATR مجمدة من الإشارة.

35. Maximum deviation from signal close
```text
entry_deviation = abs(expected_entry - signal_close)
entry_deviation_ok = entry_deviation <= 0.25 * atr_previous_at_signal
```
الوحدات: entry_deviation وsignal_close وATR price؛ 0.25 معامل؛ النتيجة boolean. لا تستبدل signal_close بسعر حي متغير لتجاوز الفحص.

36. Spread filter
```text
mid_price = (best_ask + best_bid) / 2
spread_fraction = (best_ask - best_bid) / mid_price
spread_ok = spread_fraction <= 0.0005
```
الوحدات: الأسعار price؛ spread_fraction و0.0005 fraction؛ spread_ok boolean. يلزم دفتر صالح وغير متقاطع وأسعار موجبة. الفحص على بيانات قبل الإرسال مباشرة. غيابه في OHLCV قصور، وليس spread صفرًا.

37. Order-book age
```text
maximum_order_book_age_ms = 500
order_book_age_ok = measured_order_book_age_ms <= maximum_order_book_age_ms
```
الوحدات: milliseconds وboolean. أصل measured_order_book_age_ms، وهل يعتمد event_time أم received_at أو كليهما ومزامنة الساعة، UD-05. سجل كليهما حتى يُحسم معيار التنفيذ؛ لا تختَر أحدهما بصمت.

38. Depth impact rules
```text
long_depth_impact = (expected_entry - best_ask) / best_ask
short_depth_impact = (best_bid - expected_entry) / best_bid
maximum_depth_impact = 0.001
depth_impact_ok = applicable_depth_impact <= maximum_depth_impact
```
الوحدات: الأسعار price؛ الأثر والعتبة fraction؛ النتيجة boolean. لا يتضمن هذا أثر الحركة بعد إرسال الأمر. يحاكى الدفتر عند وصول الأمر؛ حجمه حدد قبل الإرسال. اختبار حذف 50% و75% من العمق مستقل عن النموذج الأساسي. تفاصيل استهلاك الدفتر التاريخي ونموذج hidden liquidity والتجدد UD-05.

39. Participation limit
```text
recent_quote_volume = sum(quote_volume_of_last_15_completed_1m_candles)
order_notional = expected_entry * requested_quantity
participation_fraction = order_notional / recent_quote_volume
participation_ok = participation_fraction <= 0.001
```
الوحدات: الأحجام والقيمة الاسمية USDT؛ requested_quantity quantity؛ المشاركة fraction؛ النتيجة boolean. لا يستخدم حجم الدقيقة الجارية أو الحجم المستقبلي. صفر حجم أو فقد بيانات يرفض الدخول. نافذة 15 شمعة مكتملة سابقًا لكل قرار.

40. Initial stop loss
الوقف ATR only؛ ليس Channel stop ولا تركيبًا بين القناة وATR.
```text
atr_at_signal = atr_previous_at_signal
long_raw_initial_stop = entry_vwap - 2.0 * atr_at_signal
short_raw_initial_stop = entry_vwap + 2.0 * atr_at_signal
long_initial_stop = floor(long_raw_initial_stop / tick_size) * tick_size
short_initial_stop = ceil(short_raw_initial_stop / tick_size) * tick_size
```
الوحدات: جميع الأسعار وATR وtick_size price؛ 2.0 معامل؛ floor وceil تنتجان عدد ticks قبل إعادة التحويل.
LONG تقريبه للأسفل وSHORT للأعلى. الوقف الفعلي يسجل بعد التقريب. Stop Market على المنصة بمرجع Last/Contract؛ التصفية وفق Mark. إذا سعر وقف غير موجب أو لا يستوفي قيود العقد، لا توجد صلاحية تنفيذ. سياسة تقليل/إغلاق مركز امتلأ ثم أخفق فحصه UD-09.

41. R definition
```text
initial_price_risk = abs(entry_vwap - initial_stop)
initial_monetary_price_risk = original_quantity * initial_price_risk
```
الوحدات: initial_price_risk price؛ original_quantity quantity؛ initial_monetary_price_risk USDT.
initial_price_risk هو الاسم الصريح لما سمي R0 في النص السابق. ثابت بعد اكتمال الدخول وتثبيت الوقف الأولي، ولا يعاد تعريفه بعد Trailing. ليس الهامش ولا ميزانية الخسارة الشاملة للتكاليف. اعتماد لحظة تثبيته أثناء أجزاء الدخول UD-08.

42. Trailing activation
```text
long_trailing_trigger = completed_1h_close - entry_vwap >= 2.0 * initial_price_risk
short_trailing_trigger = entry_vwap - completed_1h_close >= 2.0 * initial_price_risk
trailing_active = trailing_was_active or applicable_trailing_trigger
```
الوحدات: فروق الأسعار وinitial_price_risk price؛ 2.0 معامل؛ الحالات boolean. التفعيل بإغلاق ساعة بعد التعبئة، لا بلمسة High أو Low. يظل مفعلًا بعد تفعيله. لا هدف ثابت، ولا خروج جزئي، ولا نقل تلقائي إلى التعادل عند التفعيل.

43. Trailing formula
```text
highest_close_since_entry = max(eligible_completed_1h_closes_after_entry)
lowest_close_since_entry = min(eligible_completed_1h_closes_after_entry)
long_candidate_stop = highest_close_since_entry - 3.0 * atr_current_1h_24
short_candidate_stop = lowest_close_since_entry + 3.0 * atr_current_1h_24
long_unrounded_new_stop = max(previous_effective_stop, long_candidate_stop)
short_unrounded_new_stop = min(previous_effective_stop, short_candidate_stop)
```
الوحدات: جميع الحدود والإغلاقات وATR price؛ multiplier 3.0 بلا وحدة. ATR الحالي Wilder period 24 على 1h مكتملة.
استخدم closes، لا highs/lows. تحديث كل إغلاق 1h بعد التفعيل. لا توسع الوقف. لا تجعل تحديثًا محسوبًا من إغلاق الساعة فعالًا داخل الساعة الماضية. إذا الوقف المرشح متجاوز فعليًا عند القرار، يغلق المركز. rounding للوقف المتحرك ومعالجة close عند لحظة التعبئة تمامًا UD-08 وUD-12. ترتيب أوامر cancel/replace وحماية فترة التعديل UD-08.

44. Early Failure
ثبت entry_channel_high وentry_channel_low من ساعة الإشارة. eligible_close_number يعد إغلاقات 1h بعد التعبئة.
```text
within_early_failure_window = 1 <= eligible_close_number <= 3
long_breakout_failure = within_early_failure_window and completed_1h_close <= entry_channel_high
short_breakout_failure = within_early_failure_window and completed_1h_close >= entry_channel_low
```
الوحدات: eligible_close_number عدد؛ الإغلاقات والقناة price؛ النتائج boolean. الخروج كامل المتبقي بعد القرار، لا عند إغلاق مفترض تم تنفيذه بأثر رجعي. أول ثلاثة إغلاقات ليست اشتراط مرور ثلاث ساعات كاملة؛ تفصيل لحظة المساواة مع fill_time UD-12.

45. Weak Follow-through
يفحص مرة واحدة عند سادس إغلاق ساعة مؤهل بعد التعبئة. ليس MFE من High/Low.
```text
long_close_based_mfe = max(first_6_eligible_completed_1h_closes) - entry_vwap
short_close_based_mfe = entry_vwap - min(first_6_eligible_completed_1h_closes)
applicable_close_based_mfe = long_close_based_mfe if direction_is_long else short_close_based_mfe
weak_followthrough = (eligible_close_number == 6) and (applicable_close_based_mfe < 0.5 * initial_price_risk)
```
الوحدات: mfe وinitial_price_risk price؛ 0.5 معامل؛ العداد عدد؛ النتيجة boolean. إذا جميع الإغلاقات معاكسة تكون القيمة سالبة؛ قصها عند صفر لا يغير شرط الخروج لكن لا يتم بصمت في Logging. حالة غياب إغلاق ساعتي وكيفية معالجة الفحص المتأخر UD-12 وUD-14.

46. Maximum Hold
```text
maximum_hold_seconds = 72 * 60 * 60
position_age_seconds = current_time - first_fill_time
time_exit_due = position_age_seconds >= maximum_hold_seconds
```
الوحدات: seconds؛ time_exit_due boolean. 72 ساعة من أول تعبئة، لا من آخر تحديث وقف. المؤقت التشغيلي لا ينتظر إغلاق ساعة. إذا الاتصال متعذر، سجل التجاوز ونفذ عندما تستعاد القدرة وفق سياسة الخروج المحسومة.

47. Cooldown
```text
cooldown_seconds = 6 * 60 * 60
cooldown_end = full_exit_time + cooldown_seconds
cooldown_finished = current_time >= cooldown_end
```
الوحدات: seconds وطوابع UTC وboolean. بعد إغلاق كامل الصفقة، وعلى الرمز في كلا الاتجاهين. يظل انتقال false-to-true مطلوبًا بعد التهدئة. SPEC_CONFLICT-02: جدول الحالات السابق يرسل IOC غير المنفذ إلى COOLDOWN، بينما تعريف المؤقت يبدأ فقط بعد full_exit_time؛ لا full_exit_time عند عدم التعبئة. هذا غير محسوم ضمن UD-07.

48. Position Sizing
الأسماء التالية هي تسلسل الحساب، وليست قيمًا مصطنعة لمدخلات غير متوفرة.
```text
equity = cash_balance + unrealized_pnl
risk_fraction = active_risk_fraction
portfolio_risk_capacity = 0.03 * equity - portfolio_reserved_risk
direction_risk_capacity = 0.02 * equity - same_direction_reserved_risk
risk_budget = min(risk_fraction * equity, portfolio_risk_capacity, direction_risk_capacity)
expected_entry = depth_vwap_for_candidate_quantity
long_expected_stop = floor((expected_entry - 2.0 * atr_previous_at_signal) / tick_size) * tick_size
short_expected_stop = ceil((expected_entry + 2.0 * atr_previous_at_signal) / tick_size) * tick_size
expected_stop = applicable_expected_stop
risk_distance = abs(expected_entry - expected_stop)
stop_distance_fraction = risk_distance / expected_entry
fee_reserve_per_unit = expected_entry * entry_fee_fraction + abs(expected_stop) * exit_fee_fraction
slippage_reserve_per_unit = expected_entry * stop_exit_slippage_fraction
funding_reserve_per_unit = funding_reserve_for_one_base_unit
estimated_loss_per_unit = risk_distance + fee_reserve_per_unit + slippage_reserve_per_unit + funding_reserve_per_unit
quantity_raw = risk_budget / estimated_loss_per_unit
quantity_final = floor(quantity_feasible_before_rounding / quantity_step) * quantity_step
estimated_total_loss = quantity_final * estimated_loss_per_unit
```
الوحدات: equity وcash_balance وunrealized_pnl وrisk_budget والقدرات واحتياطيات المخاطر وestimated_total_loss USDT؛ الأسعار وrisk_distance price؛ risk_fraction وstop_distance_fraction وfee fractions وslippage fraction أعداد fraction؛ احتياطيات per_unit وestimated_loss_per_unit USDT لكل quantity واحدة؛ الكميات وquantity_step quantity.
quantity_feasible_before_rounding هي أكبر كمية مرشحة تستوفي حدود المخاطر والسيولة والقيمة والهامش والتصفية قبل التقريب؛ طريقة البحث الحتمية وتوقف التقارب UD-09. لا ترفع quantity_final إلى الحد الأدنى.
```text
minimum_order_ok = (quantity_final >= minimum_quantity) and (quantity_final * expected_entry >= minimum_notional)
risk_budget_ok = estimated_total_loss <= risk_budget
minimum_trade_risk_ok = estimated_total_loss >= 0.0025 * equity
position_notional_ok = quantity_final * expected_entry <= 1.0 * equity
portfolio_risk_ok = portfolio_reserved_risk + estimated_total_loss <= 0.03 * equity
direction_risk_ok = same_direction_reserved_risk + estimated_total_loss <= 0.02 * equity
```
الوحدات: القيم النقدية USDT؛ كمية quantity؛ coefficients fractions؛ النتائج boolean.
أثر دخول الدفتر مضمّن في expected_entry؛ لا يضاف إلى estimated_loss_per_unit كخصم مستقل مرة ثانية. يعاد الحساب لتأثر السعر بالحجم، بحد أقصى 5 دورات. أعد الفحوص بعد التقريب وبعد التعبئة؛ معالجة تجاوز بعد التعبئة UD-09. equity غير موجب يمنع المداخل. لا يسمح بخطأ تقريبي يحول قدرة سالبة إلى ميزانية موجبة.

49. Risk per trade
```text
normal_risk_fraction = 0.01
reduced_risk_fraction = 0.005
minimum_actual_planned_risk_fraction = 0.0025
```
الوحدات: fraction. الحالة النشطة تعتمد Drawdown Control. لا رفع حسب score ولا تخفيض أو زيادة اعتباطية بعد خسارة فردية. الحد الأدنى يفحص بعد تقليل الحجم بالقيود وليس قبلها فقط.

50. Portfolio Risk
```text
portfolio_reserved_risk = sum(open_position_initial_risk_reservations) + sum(pending_entry_risk_reservations)
portfolio_risk_limit = 0.03 * equity
```
الوحدات: USDT. احتفظ بحجز المخاطرة الأولي طوال المركز؛ تحريك الوقف لا يحرره. لا يوجد خروج جزئي استراتيجي. طريقة تخفيض الاحتياطي أثناء إغلاق منفذ جزئيًا UD-09. انخفاض Equity قد يرفع نسبة الحجز دون دخول جديد؛ أوقف المداخل ولا تزعم سقف خسارة مضمونًا. سقف النسبة هو gate عند قبول دخول، لا ضمان خلال فجوة.

51. Direction Risk
```text
same_direction_reserved_risk = sum(risk_reservations_for_open_and_pending_same_direction_positions)
direction_risk_limit = 0.02 * equity
```
الوحدات: USDT. تجمع كل LONG معًا وكل SHORT معًا. لا تمحو مراكز الاتجاه المعاكس احتياطي الوقف، ولا يستعمل Hedge اسمي لتجاوز 3% الإجمالي.

52. Max positions
```text
maximum_concurrent_positions = 3
entry_slot_ok = open_position_count + reserved_pending_entry_slots < 3
```
الوحدات: أعداد وboolean. احتساب ما إذا يوجد Position فعلي وPending على الرمز نفسه يجب ألا يضاعف الفتحة نفسها؛ دورة الحجز والإفراج والـ reconciliation تمنع ذلك. center واحد لكل رمز.

53. Max notional per position
```text
candidate_position_notional = requested_quantity * expected_entry
position_notional_limit = 1.0 * equity
candidate_position_notional <= position_notional_limit
```
الوحدات: USDT وboolean. هذا حد اسمي وليس حد الهامش. أساس إعادة تقييم الاسمي للمراكز القائمة في gate المحفظة UD-09.

54. Max total notional
```text
gross_notional = sum(abs(open_position_notionals)) + sum(abs(pending_entry_notionals))
gross_notional_limit = 3.0 * equity
new_entry_exposure_ok = gross_notional + candidate_position_notional <= gross_notional_limit
```
الوحدات: USDT؛ 3.0 معامل؛ النتيجة boolean. لا تستخدم net_notional لتجاوز الإجمالي. يجب ألا تتكرر إضافة المرشح إذا كان محجوزًا أصلًا. تثبيت سعر تقييم open_position_notionals UD-09.

55. Margin limits
```text
position_margin_limit = 0.20 * equity
total_initial_margin_limit = 0.60 * equity
candidate_margin_ok = candidate_initial_margin <= position_margin_limit
portfolio_margin_ok = existing_initial_margin_commitments + pending_margin_reservations + candidate_initial_margin <= total_initial_margin_limit
```
الوحدات: USDT والنتائج boolean. يلزم أيضًا free_collateral كافٍ للرسوم والالتزامات وفق Adapter. الهامش النظري مقسومًا على الرافعة لا يتجاوز حساب المنصة الملزم. تثبيت initial margin commitments بعد تحرك Mark وكيف يدمج التمويل UD-09 وUD-10.

56. Leverage selection
```text
allowed_leverage_values = [1, 2, 3, 4, 5]
selected_leverage = min(leverage_that_satisfies_margin_and_liquidation_constraints)
```
الوحدات: leverage نسبة بلا وحدة. افحص الخيارات تصاعديًا للحجم الذي حدده الوقف. لا يرفع الحجم لمجرد إتاحة رافعة أعلى. إذا لا يوجد خيار صالح، خفض الكمية وكرر وفق UD-09؛ لا تتجاوز 5x. إذا لا تدعم المنصة قيمة مرشحة، ليست مؤهلة. أكّد ISOLATED وONE_WAY قبل الإرسال.

57. Liquidation calculation
لا توجد معادلة منصة نهائية موثقة في المواصفة السابقة؛ UD-10 قرار جوهري. يلزم Adapter يأخذ اتجاه المركز وquantity وentry_vwap والهامش المعزول بعد الرسوم والتمويل وشريحة Maintenance Margin وأي maintenance deduction وقاعدة رسوم التصفية وحساب Mark.
```text
liquidation_price = exchange_liquidation_model(position_state, effective_contract_rules, isolated_collateral_state)
```
الوحدات: liquidation_price price؛ position_state يحتوي quantity وprice وUSDT؛ effective_contract_rules سجل مؤرخ. الدالة متطلب غير منفذ، وليست معادلة مكتملة. يمنع تعويضها بمعادلة entry_price مع مقلوب الرافعة وإعلانها دقيقة. تحقق من نموذج Long وShort واختبارهما مقابل قيم المنصة قبل الاعتماد.

58. Liquidation buffer
```text
distance_entry_to_liquidation = abs(entry_vwap - liquidation_price)
initial_price_risk = abs(entry_vwap - initial_stop)
liquidation_distance_ok = distance_entry_to_liquidation >= 3.0 * initial_price_risk
long_liquidation_order_ok = liquidation_price < initial_stop < entry_vwap
short_liquidation_order_ok = liquidation_price > initial_stop > entry_vwap
```
الوحدات: distances وprices price؛ 3.0 معامل؛ النتائج boolean. الصيغ تنطبق على initial stop مع سعر تصفية موثوق، مع فحص قبل وبعد التنفيذ. تدهور المسافة أثناء المركز وسياسة التصرف UD-10. لا تضمن المسافة نجاة الوقف إذا قفز Mark أو تعذر التنفيذ.

59. Gap stress
اختبر تجاوز الوقف بمقدار وحدة initial_price_risk إضافية. الاختبارات الموسعة تشمل وحدتين أيضًا.
```text
gap_multiple = 1.0
long_stress_exit_price = active_stop - gap_multiple * initial_price_risk
short_stress_exit_price = active_stop + gap_multiple * initial_price_risk
long_stress_price_loss = quantity * (entry_vwap - long_stress_exit_price)
short_stress_price_loss = quantity * (short_stress_exit_price - entry_vwap)
stress_total_loss = applicable_stress_price_loss + entry_fees + stressed_exit_fees + adverse_funding_cost
```
الوحدات: gap_multiple بلا وحدة؛ prices وinitial_price_risk price؛ quantity كمية؛ الخسائر والرسوم والتمويل USDT. إن كان الوقف فوق التعادل فقد يكون price_loss سالبًا؛ لا يساوي ذلك ضمان ربح تحت سيناريو آخر.
هل السيناريو اختبار قبول دخول أم تقرير حساسية فقط، وما حد خسارته المقبول وتزامن Mark/Last، UD-10. لا تقص سعر stress غير الموجب بصمت؛ المطلوب تعريف السيناريو المقبول في القرار نفسه. القفزة موجودة في stress_exit_price فلا تطرح مرة ثانية.

60. Cost-to-risk test
المعيار المقرر 25% من الخسارة السعرية عند الوقف.
```text
risk_distance = abs(expected_entry - expected_stop)
price_loss_at_stop = requested_quantity * risk_distance
estimated_fee_reserve = requested_quantity * fee_reserve_per_unit
estimated_stop_slippage_reserve = requested_quantity * slippage_reserve_per_unit
estimated_funding_reserve = requested_quantity * funding_reserve_per_unit
embedded_cost_subtotal = estimated_fee_reserve + estimated_stop_slippage_reserve + estimated_funding_reserve
estimated_total_cost = round_trip_cost_definition_pending_UD_11
cost_to_risk_ratio = estimated_total_cost / price_loss_at_stop
cost_to_risk_ok = cost_to_risk_ratio <= 0.25
```
الوحدات: distance price؛ جميع المبالغ USDT؛ ratio و0.25 fractions؛ النتيجة boolean. إذا price_loss_at_stop صفر فالصفقة غير صالحة.
SPEC_CONFLICT-03: المعيار وُصف RoundTripCosts شامل التنفيذ، بينما نموذج sizing يضمن انزلاق الدخول داخل expected_entry، ولم يحدد مرجعًا لقياس تكلفة هذا الدخول ضمن الاختبار. إدخاله في Loss كخصم ثان يضاعفه، وحذفه من عرض التكلفة الكلية لا يمثل RoundTrip كاملة. UD-11 يحسم مرجع تكلفة الدخول وحدود استخدامه. embedded_cost_subtotal محدد حسابيًا لكن لا يُعلن أنه التعريف النهائي لـ estimated_total_cost.

61. Fees
قدر النسخة الأساسية برسوم Taker. استخدم تعرفة الحساب السارية إن كانت موثقة، وسجل maker/taker الفعلية عند التنفيذ. رسوم الدخول والخروج مستقلة وقد تختلف وفق القواعد المؤرخة. النص السابق ذكر 0.0005 لكل جانب كسيناريو عند غياب التاريخ، وليس قيمة إلزامية نهائية؛ اعتماد fallback UD-11. لا تفترض خصم BNB أو VIP. تحويل رسوم بعملة أخرى إلى USDT وزمنه UD-11.
```text
entry_fee_estimate = quantity * expected_entry * entry_fee_fraction
exit_fee_estimate = quantity * expected_stop * exit_fee_fraction
```
الوحدات: quantities quantity، prices price، fractions بلا وحدة، fees USDT. الرسم الحقيقي يسجل من كل Fill؛ رسوم التصفية منفصلة عن رسوم الخروج المعتاد.

62. Slippage
مع L2، السعر هو VWAP كمية قابلة للتنفيذ عند وصول الأمر. لا تعويض depth غير كافٍ بتعبئة كاملة. اختبار haircut ليس معرفة أن الكمية ستبقى متاحة. مكون entry impact لا يطرح نقديًا إذا دخل في Fill prices.
نموذج g المستخدم قبل الدخول لتقدير خروج الوقف على L2 غير محدد؛ UD-11. البديل الأولي عند غياب L2:
```text
sigma_1m = std(last_15_completed_1m_returns)
recent_quote_volume = sum(quote_volume_of_last_15_completed_1m_candles)
order_notional = requested_quantity * preliminary_reference_price
impact = max(0.00025, sigma_1m * sqrt(order_notional / recent_quote_volume))
slippage = 0.00025 + impact
stop_slippage = 0.00025 + 2.0 * impact
buy_fill_price = reference_price * (1.0 + slippage)
sell_fill_price = reference_price * (1.0 - slippage)
```
الوحدات: sigma_1m وimpact وslippage وstop_slippage fractions؛ volume وnotional USDT؛ quantity كمية؛ prices price. 0.00025 الأول ثابت spread-proxy، والـ max أرضية أثر وليست رسومًا.
std وsimple مقابل log returns وعدد closes المطلوب لإنتاج 15 return مدرجة في UD-01. مرجع السعر للخروج والتوقيت الذي تعاد فيه المدخلات UD-11 وUD-14. خروج الوقف يستخدم stop_slippage بدل slippage ولا يضاعف ثابت spread-proxy. هذه سيناريوهات غير معايرة، وليست قياسًا للسبريد أو أثر التنفيذ التاريخي.

63. Funding accounting
يسجل التمويل حركة نقدية عند كل تسوية فعلية، بالكمية المؤهلة وفق قاعدة المنصة. لا تستخدم المعدل النهائي المستقبلي للدخول. لا تفترض 8 ساعات ثابتة. النصاب الحدودي لمن دخل أو خرج عند settlement بالضبط UD-10 وUD-11.
```text
signed_direction = 1 if direction_is_long else -1
funding_cashflow = -signed_direction * eligible_quantity * settlement_mark_price * final_funding_rate
```
الوحدات: signed_direction عدد بلا وحدة؛ quantity كمية؛ Mark price؛ final_funding_rate fraction لكل فترة؛ cashflow USDT بإشارة، الموجب استلام. المعادلة الخطية ملزمة حيث يطابقها عقد المنصة؛ إذا كانت قاعدته مختلفة يجب توثيق اختلاف Adapter قبل الاستخدام.

64. Funding reserve model
استخدم 30 يومًا من تسويات مكتملة متاحة وقت القرار. حوّل كل معدل إلى معدل لكل ساعة بحسب طول فترته الفعلي.
```text
funding_rate_per_hour[i] = completed_funding_rate[i] / actual_interval_hours[i]
directional_paid_rate_per_hour[i] = signed_direction * funding_rate_per_hour[i]
reserve_rate_per_hour = max(0, percentile_95(directional_paid_rate_per_hour_over_previous_30_days))
funding_reserve_per_unit = expected_entry * reserve_rate_per_hour * 72
funding_reserve = requested_quantity * funding_reserve_per_unit
```
الوحدات: actual_interval_hours hours؛ rate_per_hour fraction/hour؛ 72 hours؛ expected_entry price؛ per_unit USDT لكل quantity؛ funding_reserve USDT. لا تخصم تمويلًا متوقعًا مستلمًا من مخاطرة الصفقة. لا تستخدم تنبؤًا بنهاية التمويل المستقبلي مكان تسويات مكتملة. طريقة percentile وغياب التسويات/تغير الفترات UD-01 وUD-11. الاحتياطي ثابت أقصى مدة 72 ساعة عند الدخول، وليس مصروفًا نقديًا.

65. Daily Loss Control
```text
day_start_time = current_utc_day_at_00_00
daily_return = current_equity / day_start_equity - 1.0
daily_loss_pause_trigger = daily_return <= -0.04
```
الوحدات: الطابع UTC؛ equities USDT؛ daily_return وthreshold fractions؛ trigger boolean. المعادلة للبحث الذي يمنع التدفقات الخارجية. الحي مع إيداع وسحب يحتاج UD-17.
عند التفعيل: إلغاء أوامر الدخول، منع مداخل حتى اليوم UTC التالي، وإدارة المراكز القائمة دون إلغاء حمايتها. daily pause لا يضمن أن الخسارة لن تتجاوز 4%. حالات day_start_equity غير الموجب وحدث بداية اليوم مع funding/fill تحتاج ترتيب أحداث موحد UD-12.

66. Drawdown Control
على شبكة Equity كل دقيقة:
```text
peak_equity = max(all_recorded_equity_samples_since_run_start)
drawdown_fraction = 1.0 - current_sampled_equity / peak_equity
reduce_risk_trigger = drawdown_fraction >= 0.10
hard_pause_trigger = drawdown_fraction >= 0.15
```
الوحدات: equities USDT؛ drawdown والعتبات fractions؛ triggers boolean. عند 10% تصبح مخاطرة المداخل الجديدة 0.005. تعود 0.01 عند استعادة قمة Equity السابقة؛ تعريف تخزين قمة الاستعادة أثناء تقلبها UD-17. عند 15% تلغى المداخل وتغلق المراكز بصورة منظمة ويعلق النظام للمراجعة. لا Restart تلقائي بعد التعليق في البحث. الشبكة والإيداعات والسحوبات وتعارض زمن Trigger مع Mark أسرع UD-17.

67. Pause / Resume logic
Daily pause ينتهي في اليوم التالي بشرط عدم وجود hard pause أو عطل تشغيل أو نقص بيانات. Reduced-risk ليست PAUSED؛ تسمح بمداخل بحجم أقل. Hard drawdown pause يحتاج مراجعة تشغيلية صريحة، والبحث يستمر زمنيًا دون مداخل بعد التوقف حتى نهاية الفترة.
Safety pause بسبب فشل الحماية أو reconciliation لا يرفع لمجرد بداية يوم. شروط التحقق والجهة المخولة باستئنافه UD-08 وUD-17. سجّل سبب كل Pause ووقته وحالة رفعه. لا تعِد ضبط Equity إلى قيمة جديدة لتجاوز drawdown.

68. State Machine
WARMUP: مؤشرات غير جاهزة؛ ينتقل READY عند اكتمالها.
READY: تقييم الإشارات؛ ينتقل SIGNAL_VALIDATED عند صحة الإشارة.
SIGNAL_VALIDATED: ينتقل ENTRY_PENDING بعد حجز الموارد وقبول المخاطر.
ENTRY_PENDING: ينتقل OPEN مع كمية محمية؛ عدم التعبئة له SPEC_CONFLICT-02.
OPEN: مركز محمي، يتحول TRAILING عند شرط التفعيل أو EXIT_PENDING عند خروج.
TRAILING: استمرار تحديث الوقف، ثم EXIT_PENDING.
EXIT_PENDING: لا يحرر المركز حتى تتأكد الكمية الصفرية، ثم COOLDOWN.
COOLDOWN: يعود READY بعد المؤقت، أو WARMUP إذا فقدت صلاحية البيانات.
PAUSED: بوابة حسابية أو تشغيلية للمداخل؛ لا توقف إدارة OPEN وTRAILING.
PAUSED كحالة عالمية مقابل حالة رمز UD-17. يجب ألا يطمس pause حالة مركز مطلوب حمايته. لا حالة تسمح بأمرين مستقليْن للرمز.

69. Persistent State
احفظ run_id وstrategy_version وcode_sha وconfig_hash وdata_hash وuniverse_id، وحالات الرموز والمؤشرات اللازمة، وsignal_id وorder IDs وposition_id، وأوقات الإشارة والقرار والإرسال والتأكيد والتعبئة، وكمية الأصل والمتبقي وVWAP وحدود القناة وATR المثبت وinitial_stop وinitial_price_risk، والوقف الفعال والمطلوب، ومؤقتات الخروج والتهدئة، واحتياطيات المخاطرة والهامش والفتحات، وأرصدة Cashflow وEquity والقمم وPause.
يلزم سجل أحداث لا يفقد Fill بعد Crash. آلية transaction والديمومة وتواتر checkpoint ومزامنة دفتر المنصة UD-06. لا تعد الحالة المحفوظة بديلًا عن reconciliation.

70. Restart Reconciliation
قبل دخول جديد اجلب المراكز والأوامر والتعبئات والحركات المالية، وطابقها بالحالة المحفوظة. اكتشف التعبئات أثناء الانقطاع وأعد احتساب الكميات والمخاطر. تحقق أن لكل مركز وقفًا صحيحًا على المنصة. لا تلغِ أمرًا أو تغلق مركزًا مجهول الملكية بافتراض أنه للاستراتيجية؛ علّق المداخل لحين حسم الملكية وفق UD-17.
لا تعيد إنشاء أمر ENTRY بسبب Timeout قبل الاستعلام عن client_order_id. حدود lookback وتدرج الاستعلام أثناء Rate Limit UD-06 وUD-08. اكتمال التطابق شرط Resume.

71. Order idempotency
signal_id يحدد فرصة واحدة. client_order_id يحدد نية أمر واحدة عبر retries. order_id هو معرف المنصة ولا يُخترع. fill_id وfunding event ID يمنعان الخصم المتكرر.
احفظ نية الإرسال قبل الشبكة ثم تأكيدها، مع معالجة تعطل العملية بين المرحلتين. طلب إلغاء أو تعديل متكرر يجب ألا يخلق أمرًا زائدًا. الصيغة النهائية للمعرفات وقيود طولها UD-06.

72. Protection failure behavior
كل كمية مؤكدة تحتاج حماية على المنصة. إذا تعذر تأكيدها، يغلق المركز وتعلق المداخل. لا يتم توسيع الوقف لحل خطأ API، ولا تحويل Isolated إلى Cross. مهلة تأكيد الحماية وعدد المحاولات ونوع إغلاق الطوارئ وإجراءات غياب الشبكة UD-08. هذا النقص يمنع علامة جاهزية حقيقية. حدود الدخول الخاصة بالانزلاق لا يجوز أن تترك إغلاق خطر معلقًا.

73. Data outage behavior
أوقف المداخل الجديدة عند فقد بيانات لازمة. اترك الوقف المؤكد على المنصة. بعد الاستعادة طابق التعبئات والمركز ثم نفذ خروجًا واجبًا ومتأخرًا، وسجل مدة التجاوز. لا تحتسب وقت انقطاع البوت كإيقاف مؤقت لعمر المركز. مرور ساعة دون تحديث لا يسمح باستخدام إشارة قديمة. شروط freshness لكل مصدر غير Book وحددتها المواصفة UD-04 وUD-14؛ لا تعوض Mark مفقودًا بـ Last بصمت.

74. Delisting behavior
اشمل الشطب والتسوية القسرية في البيانات والتقرير. لا تحذف آخر صفقة أو يوم الرمز من النتائج. خروج الرمز من Universe ليس شطبًا. عند إعلان شطب متاح وقت القرار، سياسة إيقاف المداخل/الإغلاق قبل التسوية UD-13. عند تسوية فعلية سجل السعر والرسوم والكمية وسبب الخروج الحقيقي. لا تستخدم إعلانًا لم ينشر بعد لمنع دخول تاريخي.

75. Accounting model
دفتر حركات منفصل للمحقق والرسوم والتمويل والتدفقات الخارجية. الهامش المحجوز ليس مصروفًا ولا يخصم مرة أخرى من Equity. احتياطي المخاطرة والتكاليف ليس خسارة فعلية. الربح حسب Fill prices الفعلية، والتمويل مرة واحدة، والانزلاق تفسير فرق سعر لا Cashflow ثانية.
```text
ending_cash = starting_cash + sum(realized_gross_pnl_events) - sum(fee_expense_events) + sum(signed_funding_cashflows) + sum(net_external_cashflows)
```
الوحدات: جميع المدخلات والمخرجات USDT. margin transfer بين Wallet وIsolated ليس external_cashflow. reconciliation يميز نقل الضمان عن الربح.

76. Equity definition
```text
cash_balance = total_strategy_collateral_after_realized_cashflows
unrealized_pnl = sum(open_position_unrealized_pnl)
equity = cash_balance + unrealized_pnl
```
الوحدات: USDT. cash_balance يشمل الضمان المحجوز ويستبعد أموالًا ليست للاستراتيجية؛ free_collateral مفهوم منفصل. قياس allocated strategy collateral في حساب مشترك UD-17. Equity تقييم Mark لا سعر إغلاق اعتباطي. اقتران Equity الدقيقة ببيانات Mark المتاحة UD-17.

77. Mark Price use
Mark لقياس Equity والتصفية. Last للقناة والإشارة ومرجع Stop trigger المعتمد. لا يعني تفعيل Stop على Last أن التصفية تنتظره. احفظ السلسلتين ووقت إتاحتهما. توقيت maintenance checks تحت Mark داخل الدقيقة UD-10 وUD-14. Mark المتأخر لا يعاد ختمه كتحديث جديد.

78. Realized PnL
```text
long_realized_gross_pnl = exit_quantity * (exit_fill_price - allocated_entry_vwap)
short_realized_gross_pnl = exit_quantity * (allocated_entry_vwap - exit_fill_price)
trade_net_pnl = sum(realized_gross_pnl_for_trade) - entry_fee_total - exit_fee_total + signed_funding_total
```
الوحدات: quantities quantity؛ prices price؛ pnl والرسوم والتمويل USDT. لا إضافات للمركز، لكن أجزاء دخول IOC تكون VWAP واحدًا عند اكتماله. allocation إذا خرج جزء اضطراريًا قبل اكتمال جميع تعبئات الدخول UD-08. الصفقة المفتوحة لا تحمل exit_price مختلقًا.

79. Unrealized PnL
```text
long_unrealized_pnl = remaining_quantity * (current_mark_price - entry_vwap)
short_unrealized_pnl = remaining_quantity * (entry_vwap - current_mark_price)
```
الوحدات: quantity، price، والنتيجة USDT. لا تخصم رسوم خروج مستقبلية من PnL الرسمي بصمت؛ تقدير liquidation/closeout equity يحتاج تعريفًا مستقلًا إن أضيف لاحقًا. الرسوم المدفوعة موجودة في Cash.

80. Fees accounting
حركة Fee لكل Fill مرة واحدة، مع نوع السيولة والعملة وسعر التحويل إذا لزم. سعر expected_stop في sizing تقدير؛ الرسم الحقيقي يعتمد notional التعبئة الفعلي، وخاصة بعد فجوة. لا تجمع تقرير الرسوم ثم تخصمه مرة ثانية من equity المتغير بها. Maker rebate إذا وجد يسجل بإشارته مع تعريف موحد؛ حقول المصروف السالب UD-11.

81. Funding accounting
هذا القسم تكرار مطلوب للتأكيد المحاسبي، وليس عملية ثانية. كل settlement له source_id فريد وسجل Cashflow واحد. ربطه بالصفقة للتقرير لا يعيد خصمه من الرصيد. طبق معادلة القسم 63 عند تحقق دلالة المنصة. عند صفر quantity مؤهلة لا توجد دفعة للمركز. التمويل النهائي التاريخي معروف للمحاسبة بعد حدوثه، وليس معلومة للدخول قبله.

82. Slippage accounting
```text
buy_execution_shortfall = fill_quantity * (fill_price - reference_price)
sell_execution_shortfall = fill_quantity * (reference_price - fill_price)
```
الوحدات: quantities quantity؛ prices price؛ shortfall USDT. المرجع يحتاج نوعًا صريحًا reference_type، ومصدرًا وزمنًا؛ لا تخلط arrival_mid مع best_bid/ask أو signal_close. تعريف المرجع الأساسي للتقرير UD-11. shortfall تحليل للتنفيذ داخل Fill prices، ولا يطرح ثانية من trade_net_pnl. gaps في Fill prices لا تُخصم مرة ثانية كذلك.

83. Backtest execution model
المحرك Event-driven. Signal Engine واحد بين البحث والحي، وتختلف طبقة التنفيذ المعلنة فقط. مع Trades/Quotes/L2 تحدد نية الدخول على المعلومات المتاحة، ثم يحاكى وصول الأمر وتعبئته وفق الأحداث التالية؛ لا تستعمل المستقبل لتحسين كمية القرار. لا تفترض ملء كامل بمجرد لمس Limit.
النموذج الأولي دون L2:
```text
preliminary_available_at = signal_time + 2_seconds
preliminary_decision_time = max(required_preliminary_available_at_values)
reference_minute_start = first_1m_interval_start_strictly_after(preliminary_decision_time)
preliminary_reference_price = open_price_at_reference_minute_start
```
الوحدات: الطوابع UTC والإضافة seconds؛ reference_price price. يضاف نموذج القسم 62، وتطبق فحوص عدم المطاردة والمهلة. لا يدخل عند close الإشارة. لا يعرف النموذج OHLCV السبريد الحقيقي وعمق IOC والتعبئات الجزئية.
وسم التقرير إلزامي: Preliminary - execution assumptions unverified.
SPEC_CONFLICT-01: اشتراط stale-book/spread/depth لكل دخول يتعارض تشغيليًا مع السماح باختبار OHLCV دون هذه البيانات، ولم تحدد المواصفة طريقة تمثيل هذه gates في الوضع الأولي. UD-14 يحسم بروتوكول الاختبار دون تسميته تنفيذًا دقيقًا.
Freqtrade طبقة تشغيل محتملة وفق النص السابق؛ لا يعتمد Backtest الافتراضي كمرجع تنفيذ دقيق. يحتاج المرجع تحكمًا في Universe التاريخية وavailable_at واحتياطي المخاطر وMark والتمويل والتصفية والتعبئات. اسم البرنامج وإصداره والتكامل UD-16. جهة واحدة فقط ترسل الأوامر.

84. Intrabar ambiguity handling
لا تفترض ترتيب High وLow داخل 1m أو 1h. لا تمنح وقفًا جديدًا أثرًا قبل exchange acknowledgement. لا تعبئة تلقائية عند stop_price إذا أول سعر بعد فجوة أسوأ. إذا تزامن Mark liquidation مع Last stop داخل شمعة غير مفككة، الترتيب مجهول. السياسة العددية الحتمية للحالات الملتبسة لم تعتمد في PVB-24؛ UD-14. سجل ambiguous_event_count والتأثير الحساس للسياسة، ولا تنقل افتراض CBOF السابق إلى هذه النسخة بصمت.

85. Mark vs Last Price
احتفظ بتدفقيْن ومصدرين وتوقيتين. Last: شموع الإشارة، سعر السوق للتنفيذ، trigger الوقف المحدد. Mark: UPNL وEquity وliquidation. بيانات Mark 1m لا تثبت توقيت عبور intrabar مقارنة بـ Last tick. عدم توفر Mark يغلق باب الادعاء بإثبات غياب التصفية، حتى لو اكتمل اختبار إشارات السعر.

86. Historical contract rules
خزن نسخ effective_from/effective_to لtick_size وquantity_step وmin/max quantity وminimum_notional وleverage brackets وmaintenance parameters وأنواع الأوامر وجداول التمويل والرسوم وتواريخ التداول والشطب.
لا تستعمل قواعد اليوم كتاريخ مؤكد. إذا اقتصر البحث على سيناريو ثابت معلن فلا يوصف Exact historical replay. صلاحية استخدامه للقبول UD-10 وUD-13 وUD-14. لا تحذف رموزًا انتقائيًا فقط لأن تاريخ قواعدها صعب ثم تقارن الربحية بلا تقرير التغطية.

87. Walk-forward design
داخل Development وValidation فقط: 18 شهرًا سابقة، ثم 3 أشهر تقييم، ثم تحريك 3 أشهر. ابدأ حين تتوفر نافذة كاملة. المعايير الأساسية ثابتة، لا Hyperopt ربع سنوي. معايرة تكلفة من الماضي فقط إن توفرت بياناتها. إذا استخدمت labels لنتائج صفقات، افصل التدريب عن التقييم 72 ساعة لمنع تداخل horizon.
تهيئة المؤشرات من الماضي مسموحة. لا تصفر الحساب بعد خسارة عند بداية كل ربع. التقرير النهائي يحتوي Replay متصلًا. قواعد carry positions عبر حدود النوافذ وموضع purge الدقيق ونقطة بداية التقويم UD-18. لا تصلح نافذة اختبار لاختيار قواعدها نفسها.

88. Development / Validation / Final Test split
الفترة المستهدفة من 2020-01-01 حتى 2026-08-31، حسب توفر العقود، وليست إقرارًا بأن البيانات موجودة فعليًا.
Development: 2020-01-01 حتى نهاية 2023-12-31.
Validation: 2024-01-01 حتى نهاية 2025-06-30.
Final Test: 2025-07-01 حتى نهاية 2026-08-31.
التعبير نصف المفتوح لهذه الفترات:
```text
development_interval = [2020-01-01T00:00:00Z, 2024-01-01T00:00:00Z)
validation_interval = [2024-01-01T00:00:00Z, 2025-07-01T00:00:00Z)
final_test_interval = [2025-07-01T00:00:00Z, 2026-09-01T00:00:00Z)
```
الوحدات: طوابع UTC. هذه تحويلات حدود تاريخية للمواعيد نفسها، لا تغيير لتقسيمها.
لا يسمى Final Test untouched إذا سبق استخدامه في اختيار القواعد. عند التلوث يوصف Retrospective وتلزم فترة مستقبلية بعد تجميد الإصدار، 90 يومًا على الأقل وتمتد إذا نقصت العينة. تدقيق تلوث العينة UD-18.
أحجام الحساب المذكورة سابقًا 200 و1000 و10000 USDT كانت سيناريوهات مقترحة لا اختيارًا للحساب المرجعي. اعتماد run sizes والحجم الذي تقاس عليه بوابة القبول UD-18. لا تعرض نتائج قبل التنفيذ.

89. Stress Tests
أعد تشغيل المحرك لكل سيناريو، ولا تضرب Net PnL النهائي بعامل. ثبت بقية الإعدادات ومدخلات البيانات.
- Base: الرسوم ونموذج التنفيذ الموثقان بعد حسم UD.
- 1.5x: الرسوم والسبريد والأثر مضروبة في 1.5.
- 2x: العناصر نفسها مضروبة في 2.0.
- Fees only: زيادة الرسوم وحدها؛ مقدار هذه الزيادة المستقلة UD-19.
- Slippage only: مكون الأثر مضروب في 2.0 ثم 3.0، مع فصل spread-proxy.
- Latency: تأخير إضافي 5 و30 و60 seconds؛ انتهاء صلاحية الإشارة يؤدي لإلغائها.
- Depth: إزالة 50% ثم 75% من عمق الدفتر؛ توزيع الحذف وآلية replay UD-05.
- Rejections: رفض 1% ثم 5% من المداخل، ببذرة مسجلة غير مختارة بعد النتائج؛ قيمة البذرة UD-19.
- Outages: انقطاع 5 و30 minutes مع بقاء أوامر المنصة؛ جدول بداية الانقطاع UD-19.
- Gap: خروج أسوأ من الوقف بـ 1.0 ثم 2.0 initial_price_risk.
- Funding: زيادة التمويل المدفوع 50% دون تحسين التمويل المستلم.
- Parameter sensitivity واحدًا في كل مرة: قناة 20 و24 و28 hours؛ RVOL 1.3 و1.5 و1.7؛ Stop 1.75 و2.0 و2.25 ATR؛ Trailing 2.5 و3.0 و3.5 ATR.
لا تختبر حاصل ضرب الشبكة لاختيار أفضل خلية. تغيير Threshold صغير ينسف الربحية علامة هشاشة. أثر Stress على حجز الحجم وإلغاء الإشارات جزء من النتيجة؛ لا تثبت الصفقات بشكل مصطنع.

90. Ablation Tests
A: Full PVB-24.
B: حذف فلتر RVOL فقط.
C: حذف هامش 0.10 ATR، مع إبقاء تجاوز القناة وانتقال الحالة.
D: حذف Early Failure فقط.
E: حذف Weak Follow-through فقط.
F: حذف Trailing؛ يبقى الوقف الأولي والوقت وسائر شروط النسخة، اختبار تشخيصي.
قارن محفظة فعلية بقيودها، وسجل أحداث مستقل بوحدة مخاطرة معيارية لعزل أثر انخفاض التعرض. تصميم سجل الأحداث المستقل وتكاليفه تحت تضارب الإشارات UD-19. كل Ablation يغير المكون المسمى فقط.
لا اختبار حذف OI أو Taker لأنهما غير موجودين. إضافتهما FUTURE_RESEARCH_ONLY. عدم فائدة الحجم يرفض فرضية المشاركة الحجمية؛ الاختراق الأبسط يحتاج إصدارًا واختبارًا مستقلين قبل اعتماده.

91. Regime Diagnostics
تصنيف تقريري لا Gate دخول. الحساب من معلومات BTC السابقة والمتاحة.
```text
btc_return_30d = btc_latest_available_close / btc_close_30d_earlier - 1.0
bull_regime = btc_return_30d > 0.10
bear_regime = btc_return_30d < -0.10
sideways_regime = -0.10 <= btc_return_30d <= 0.10
log_return_1h[t] = ln(btc_close_1h[t] / btc_close_1h[t-1])
annualized_volatility = std(last_30_days_completed_log_returns_1h) * sqrt(24 * 365)
high_volatility = current_annualized_volatility > percentile_75(previous_year_volatility_history)
low_volatility = current_annualized_volatility < percentile_25(previous_year_volatility_history)
```
الوحدات: الأسعار price؛ returns fractions؛ annualized_volatility fraction على مقياس سنوي؛ التصنيفات boolean. 30 يومًا تعادل 720 شمعة 1h عند اكتمالها. std وquantile وتواتر عينات previous_year والشمعة المرجعية لعائد BTC UD-01 وUD-20. دون سنة مرجعية كاملة التصنيف UNCLASSIFIED؛ لا تحذف الصفقة. High/Low التقلب مستقلان عن Bull/Bear/Sideways.

92. LONG/SHORT separation
أخرج تقرير LONG وحده وSHORT وحده بتكاليفهما وتمويلهما، ثم المحفظة المشتركة. running LONG-only وSHORT-only منفصلًا يعيد توزيع الفتحات والمخاطر؛ يميز عن تقسيم صفقات run مشترك. يجب عرض نوع التقرير كي لا يقارن تحسن التعرض بتحسن الإشارة. لا تخصص معايير جديدة لكل اتجاه داخل v1.0.

93. Symbol-level analysis
لكل رمز: عدد الصفقات، صافي الربح، PF، متوسط الخسارة والربح، الزمن والتكلفة والتمويل، أهلية Universe والتغطية وأسباب الرفض، ومساهمة أفضل رمز في إجمالي الربح. افصل سنة/ربع وشرائح السيولة والتكلفة. حدود الشرائح لم تحدد؛ UD-20.
إزالة أفضل 5 صفقات تحليل حساسية. ترتيبها حسب Net PnL بالعملة مقابل R، وإعادة Replay أو حذف المساهمة المحاسبية فقط، UD-19. لا تعتبر تحول النتيجة لخسارة وحده برهانًا نهائيًا ضد استراتيجية اتجاه؛ يكشف تركّزًا وضعفًا في حجم الدليل. لا تحذف أفضلها ثم تخفي هذا الاختبار.

94. Weekly return analysis
الأسبوع الاثنين 00:00 UTC إلى الاثنين التالي. استخدم Equity بما فيها المراكز المفتوحة، لا أرباح الصفقات المغلقة فقط. الأسابيع الكاملة مقام النسب، والجزئية تقرير منفصل. rolling seven-day returns تقرير إضافي لا يخلط بالأسابيع غير المتداخلة.
```text
weekly_return = week_end_equity / week_start_equity - 1.0
mean_weekly_return = mean(full_week_returns)
median_weekly_return = median(full_week_returns)
best_week = max(full_week_returns)
worst_week = min(full_week_returns)
losing_week_fraction = count(weekly_return < 0) / full_week_count
weeks_at_least_25 = count(weekly_return >= 0.25)
weeks_at_least_50 = count(weekly_return >= 0.50)
weeks_at_least_100 = count(weekly_return >= 1.00)
```
الوحدات: equity USDT؛ العوائد وlosing_week_fraction fractions؛ weeks/count أعداد. أخرج نسبة كل عدد من full_week_count. العينات الصفرية أو المقام غير الموجب تعطي حالة غير معرفة لا رقمًا تجميليًا. تدفقات الحي الخارجية UD-17.
مقاييس التقرير الأخرى ملزمة، ولا تحذف بحجة أن عنوان القسم أسبوعي:
```text
net_return = ending_equity / initial_equity - 1.0
cagr = (ending_equity / initial_equity) ** (365 / elapsed_days) - 1.0
profit_factor = sum(positive_trade_net_pnl) / abs(sum(negative_trade_net_pnl))
trade_r_multiple = trade_net_pnl / initial_reserved_risk
expectancy_usdt = mean(trade_net_pnl)
expectancy_r = mean(trade_r_multiple)
win_rate = count(trade_net_pnl > 0) / closed_trade_count
average_win = mean(trade_net_pnl_where_positive)
average_loss = mean(trade_net_pnl_where_negative)
median_trade = median(trade_r_multiple)
daily_return = equity_at_day_end / equity_at_day_start - 1.0
sharpe = mean(daily_returns) / std(daily_returns) * sqrt(365)
sortino = mean(daily_returns) / downside_deviation * sqrt(365)
calmar = cagr / maximum_drawdown
average_exposure = time_weighted_mean(gross_open_notional / equity)
```
الوحدات: Net Return وCAGR وWin Rate وDrawdown fractions؛ Average Win/Loss وExpectancy USDT نقدية؛ trade_r_multiple وSharpe وSortino وCalmar وExposure نسب؛ elapsed_days days. CAGR يعرض لمدة سنة أو أكثر فقط؛ لا يطبق عندما equity غير موجبة.
Maximum Drawdown من سلسلة الدقيقة؛ Time Under Water أطول مدة دون استعادة القمة؛ Longest Losing Streak حسب إغلاق الصفقات. تعريف downside_deviation في النص السابق محتمل لأكثر من مقام؛ UD-01. tie-breaking لترتيب إغلاقات متزامنة UD-12. القسمة على صفر توصف undefined أو infinite حسب المعنى، لا صفرًا.
أخرج Trade Count وFees وFunding وSlippage/Shortfall وAverage Holding Time وLiquidations وRejected Entries وPause Durations وCapacity Limits. لا تخصم shortfall ثانية من PnL.

95. Acceptance Criteria
البوابة المقترحة في المصدر تثبت قبل Final Test. هذه قواعد قرار بحثي وليست ضمانًا:
- صافي خارج العينة موجب بعد التكاليف.
- PF خارج العينة 1.15 على الأقل.
- الحد الأدنى لفاصل ثقة 95% لمتوسط العائد اليومي موجب.
- الصافي موجب عند 1.5x execution costs.
- لا تصفيات في Base.
- Maximum Drawdown لا يتجاوز 20% في Base، مع تطبيق Hard pause عند 15% فعليًا.
- عدم اعتماد الربح على خلية Threshold وحيدة.
- لا أخطاء سببية أو محاسبية.
- اكتمال العينة أو تصنيف الدليل غير كافٍ.
- النظام لا يقضي معظم الاختبار متوقفًا بسبب فشل إدارة المخاطر.
```text
numeric_acceptance_gates = (
    out_of_sample_net_pnl > 0
    and out_of_sample_profit_factor >= 1.15
    and lower_95_confidence_bound_daily_mean > 0
    and net_pnl_at_1_5_execution_costs > 0
    and base_liquidation_count == 0
    and base_maximum_drawdown <= 0.20
)
```
الوحدات: PnL USDT؛ PF نسبة؛ العائد وdrawdown fractions؛ count عدد؛ الناتج boolean. numeric_acceptance_gates وحدها لا تكفي لتعلن acceptance بسبب بوابات جودة وقرارات UD-18 وUD-19.
فشل 2x ليس رفضًا آليًا إذا كان بعيدًا عن التنفيذ المقاس؛ إذا التنفيذ المقاس قريب منه وتختفي الربحية فالنسخة مرفوضة للتشغيل. بعد قبول مبدئي، Paper 90 يومًا على الأقل وقياس التنفيذ. Paper لا يثبت مكان الأمر الحقيقي في طابور المنصة.

96. Rejection Criteria
ارفض ادعاء Edge مثبت إذا تظهر أخطاء سببية/محاسبية، أو يغيب الصافي بعد التكاليف المعقولة، أو تنهار النتيجة مع تغييرات صغيرة، أو لا يضيف الحجم تحسينًا مستقرًا للفرضية المسماة. عدم توفر حجم عينة أو بيانات تنفيذ كافية يعني INCONCLUSIVE لا نجاحًا مزيفًا ولا بالضرورة رفض آلية اقتصادية نهائيًا.
لا ترفع الرافعة لإنقاذ فشل الإشارة. لا تعالج غياب أسابيع مضاعفة برفع مخاطرة بعد الخسارة. حد تركّز أفضل رمز/حدث، وقياس هشاشة Threshold، وتعريف معظم الفترة متوقفًا، غير رقميين في المصدر؛ UD-19.

97. Statistical Sample Requirements
300 صفقة خارج العينة على الأقل، 100 لكل اتجاه على الأقل، و52 أسبوعًا كاملًا على الأقل، وتمثيل لأكثر من Regime. الصفقات المتزامنة على عملات مترابطة ليست أحداثًا مستقلة.
Bootstrap على كتل أيام المحفظة معًا، طول أساسي 7 أيام، وحساسية 3 و14 يومًا، وعدد إعادة سحب 5000. Confidence level 95%. طريقة blocks وفاصل الثقة والبذرة UD-19. لا تستخدم IID trades bootstrap وتتجاهل الارتباط.
حفظ جميع التجارب بما فيها الفاشلة إلزامي. فاصل الثقة مشروط بالعينة ولا يولد أزمة لم تظهر فيها. إن لم تكف العينة، النتيجة INCONCLUSIVE وتمدد المراقبة دون إجبار صفقات.

98. Unit Tests
اختبر على بيانات مصنوعة معلنة للاختبار البرمجي فقط، لا تعرضها كـ Backtest أرباح:
- channel يستبعد شمعة الإشارة.
- ATR السابق للإشارة وATR الحالي للTrailing وبذرة Wilder.
- median الحجم يستبعد t ومعالجة zero/missing.
- strict > و< للمخترق و>= لـ RVOL.
- الحالة السابقة تستخدم t-25 حتى t-2 وATR t-2.
- previous unknown لا يتحول false.
- فترة التهدئة وساعة السادسة وأول ثلاثة إغلاقات وحد 72 ساعة.
- حدود available_at وexpiry بعد حسم inclusive policy.
- rounding tick/step لكل اتجاه، ومنع rounding كمية لأعلى.
- initial_price_risk ثابت لا يتغير مع وقف متحرك.
- Trailing يعتمد close وليس high/low ولا يتراجع.
- risk sizing وتكاليف per_unit وfunding reserve والحد الأدنى 0.0025.
- المخاطرة المحجوزة والاتجاه والفتحات تحت التزامن.
- رسوم وتمويل وأثر سعر لا تخصم مرتين.
- معادلات Realized/Unrealized وMark/Last.
- Daily loss وDrawdown وResume والتدفقات الخارجية بعد حسمها.
- null وzero والبيانات المفقودة لا تنتج أوامر.
- تطابق الحساب الدفعي وReplay، وإلحاق بيانات مستقبلية لا يغير الماضي.
كل اختبار مع expected behavior من قسم محدد. بند UD لا يمثّل كسلوك ناجح حتى يحسم.

99. Integration Tests
Replay يحاكي IOC بلا تعبئة وبأجزاء، وAck ضائع وFill متأخر وCancel متأخر، وRestart بين حجز المخاطرة والإرسال، وانقطاع مصدر السوق أو المنصة، وفشل إنشاء وقف وتعديله. تحقق من reconciliation وidempotency والكمية المخفضة ومنع انقلاب المركز.
اختبر تحديث Universe والشطب وFunding متزامنًا مع خروج، وRate limit وclock skew وMark gap قبل Last stop، وتجاوز min notional بعد تقريب. قارن إشارات المحرك المرجعي بطبقة Freqtrade المثبتة، وحساب liquidations مع Adapter والقيم المرجعية.
شغل lookahead analysis وrecursive indicator checks كفحوص مساعدة؛ لا تعد نجاحها إثباتًا لسلامة كل البيانات الخارجية. بيانات اختبار التصفيات والشرائح مصدرها موثق وليست guessed constants.

100. Logging
لكل candidate سجل جميع مدخلاته وتوقيتها وحالتها ومفاتيح الترتيب ونتائج كل Gate، مع primary_rejection_code وall_rejection_codes. سجل النية والحجز والإرسال والتأكيد والتعبئة والإلغاء وتعديل الوقف ومصدر Clock وأسباب Pause وResume.
لا تحفظ API keys أو التواقيع أو الأسرار في logs. خطأ API مع رمز وعلاقة بالـ order دون كشف credentials. بيانات مرجعية للسبريد وdepth والانزلاق والمدخلات الناقصة تمكن إعادة القرار. لا تكتف بتسجيل المنفذ وتخفي المرفوض.

101. Rejection Codes
الأكواد المعتمدة: NOT_IN_UNIVERSE, WARMUP_INCOMPLETE, DATA_GAP, DATA_NOT_AVAILABLE, STALE_SIGNAL, NO_NEW_BREAKOUT, LOW_RVOL, COOLDOWN, POSITION_EXISTS, STALE_BOOK, SPREAD_TOO_WIDE, EXCESSIVE_IMPACT, ENTRY_TOO_FAR, BREAKOUT_REVERSED, COST_TOO_HIGH, MIN_NOTIONAL, MIN_QUANTITY, PORTFOLIO_RISK_LIMIT, DIRECTION_RISK_LIMIT, MARGIN_LIMIT, EXPOSURE_LIMIT, LIQUIDATION_BUFFER_FAIL, DAILY_PAUSE, DRAWDOWN_PAUSE, ORDER_REJECTED, IOC_UNFILLED, PROTECTION_FAILURE.
احفظ جميع الأسباب لا الأول فقط. ترتيب primary code، وربط أقصى deviation وعمر الإدراج وpending_entry بالأكواد المناسبة، وطريقة إضافة أسباب stale-mark وunsupported-contract والتقارب UD-06 وUD-09 وUD-15. لا تصنف rejection كصفقة خاسرة.

102. CSV schemas
الملفات المنطقية التالية جميعها مطلوبة عند التنفيذ اللاحق؛ هذا التسليم TXT واحد فقط.
أنواع منطقية: string، enum، boolean، integer، decimal، utc_timestamp، string_list. الحقول ذات الزمن لا تختلط بالمدد. جميع الصفوف ترتبط بـ run_id. الحقول غير المنطبقة nullable ومميزة عن numeric zero. serialized encoding للفواصل والقوائم وnull والطوابع UD-15.

runs.csv: صف لكل تشغيل.
run_id:string primary key; strategy_version:string; code_sha:string; config_hash:string; data_hash:string; mode:enum; start_time:utc_timestamp; end_time:utc_timestamp nullable أثناء التشغيل; initial_equity:decimal USDT; seed:integer; cost_model_id:string.

signals.csv: صف لكل إشارة/قرار مرشح مسجل.
run_id:string; signal_id:string primary identity ضمن التشغيل; symbol:string; side:enum LONG/SHORT; event_time:utc_timestamp; interval_start:utc_timestamp; interval_end:utc_timestamp; available_at:utc_timestamp; decision_time:utc_timestamp; channel_high:decimal price; channel_low:decimal price; atr_previous:decimal price; rvol:decimal ratio; universe_id:string; accepted:boolean; rejection_codes:string_list; primary_rejection_code:string nullable.
بيانات إضافية لازمة لإعادة القرار من Logging: previous/current breakout states، signal_close وRVOL inputs، ترتيب batch، data references، signal_order_deadline، risk gate values. توحيد أعمدة هذه الإضافات نهائيًا UD-15.

orders.csv: صف الحالة النهائية لكل أمر، مع سجل أحداث تغييره في Logging.
run_id:string; order_id:string nullable قبل Ack; client_order_id:string; signal_id:string nullable للخروج المرتبط بالمركز; position_id:string; type:enum; side:enum BUY/SELL; quantity:decimal quantity; limit_price:decimal price nullable; trigger_price:decimal price nullable; order_sent_at:utc_timestamp; exchange_ack_at:utc_timestamp nullable; status:enum; reject_reason:string nullable.

fills.csv: صف لكل تعبئة فعلية.
run_id:string; fill_id:string; order_id:string; event_time:utc_timestamp بوصف fill_time; received_at:utc_timestamp; quantity:decimal quantity; price:decimal price; fee:decimal بوحدة fee_asset; fee_asset:string; liquidity_role:enum; reference_bid:decimal price nullable; reference_ask:decimal price nullable; reference_mid:decimal price nullable. تحويل Fee إلى USDT وreference_type/source timestamp يلزمان UD-11 وUD-15.

positions.csv: صف لكل مركز مفتوح أو مغلق.
run_id:string; position_id:string; symbol:string; side:enum; first_fill_at:utc_timestamp; exit_at:utc_timestamp nullable; original_quantity:decimal quantity; remaining_quantity:decimal quantity; entry_vwap:decimal price; exit_vwap:decimal price nullable; initial_stop:decimal price; initial_price_risk:decimal price; initial_risk:decimal USDT; leverage:integer; margin:decimal USDT; gross_pnl:decimal USDT; fees:decimal USDT; funding:decimal signed USDT; net_pnl:decimal USDT; exit_reason:enum nullable للمفتوح.
margin يجب أن يميز initial/current في المخطط المادي بعد حسم UD-09؛ لا تخزن قيمتين مختلفتين تحت معنى واحد.

stop_events.csv: صف لكل طلب/تأكيد تعديل وفق UD-15.
run_id:string; position_id:string; event_time:utc_timestamp; old_stop:decimal price nullable عند الإنشاء; new_stop:decimal price; reason:enum; requested_at:utc_timestamp; effective_at:utc_timestamp nullable حتى التأكيد.

cashflows.csv: صف لكل حركة نقدية.
run_id:string; id:string; position_id:string nullable; timestamp:utc_timestamp; type:enum; signed_amount:decimal; asset:string; source_id:string. conversion_to_usdt مرجعه UD-11. لا تدخل احتياطيات المخاطر كمصروف.

equity.csv: صف كل دقيقة.
run_id:string; timestamp:utc_timestamp; cash:decimal USDT; unrealized_pnl:decimal USDT; equity:decimal USDT; margin:decimal USDT; gross_exposure:decimal ratio; net_exposure:decimal signed ratio; reserved_risk:decimal USDT; drawdown:decimal fraction; pause_state:enum.
تعريف price timestamp في كل صف وخروج آخر فترة وما إذا pending يدخل exposure العرض UD-09 وUD-17.

103. Parquet schemas
نفس الجداول المنطقية والحقول والوحدات والعلاقات في القسم 102، دون فقد حقول عند تحويل CSV إلى Parquet. decimal لا يتحول float بصمت. Nulls فعلية؛ القوائم تبقى قوائم منطقية؛ timestamp يحمل UTC.
precision/scale وtimestamp unit وcompression وpartitioning وschema_version وenum encoding وprimary/foreign key enforcement قرارات UD-15. لا نختَر قيمًا من المكتبة ونصف المخطط بأنه نهائي. حافظ على Unicode للرموز النصية مع بقاء المعادلات ASCII في هذه الوثيقة.

104. Run metadata
يسجل strategy_version وcode_sha وconfig_hash وdata_hash وrun_id ووقت البدء والنهاية والبيئة وإصدارات التنفيذ وmode وinitial_equity وcost_model_id وseed وtimezone UTC ومدة الاختبار وحالة clean git وmanifest لتجارب Ablation/Stress وقرارات UD المحسومة.
سجل status للتشغيل مكتمل/فاشل/متوقف بسبب الخطر دون حذف بيانات التوقف. لا تسمح لـ run صامت بإعدادات مختلفة تحمل config_hash نفسه. معلومات العلم بأن Final Test سبق رؤيته تدخل metadata.

105. Data hashes
ثبّت ملفات المصدر ونسخ التصحيح وتوقيت تنزيلها ومعرف مصدرها وChecksums وmanifest التغطية. data_hash يربط المدخلات الفعلية بما فيها Mark وFunding والقواعد وUniverse. خوارزمية التجميع وترتيب الملفات والبايتات UD-16. لا تستخدم اسم الملف بدل hash محتوى. تصحيح الأرشيف ينشئ هوية بيانات جديدة ولا يكتب فوق run قديم بلا أثر.

106. Config hashes
config_hash يشمل المعايير، مخاطر المحفظة، نموذج التنفيذ، الرسوم، البذرة، delays، قواعد البيانات الناقصة، قواعد rounding وتوقيت الأحداث، وسياسات حل UD، لا مؤشراتها وحدها. Serialization canonization وخوارزمية hash UD-16. الأسرار مستبعدة، لكن تغيير مؤثر في نتائج البحث لا يختفي بسبب تصنيف خاطئ كسر تشغيلي.

107. Reproducibility commands
لم يُسلَّم مستودع أو CLI أو code_sha أو إصدار Freqtrade أو ملفات تنفيذ؛ لذلك لا توجد أوامر حقيقية يمكن اعتمادها الآن. لا يحتوي هذا الملف أوامر تشغيل مختلقة أو مسارات لبرامج غير موجودة. UD-16 يطلب تسليم الأوامر الفعلية بعد البناء لهذه العمليات:
- التحقق من البيانات وmanifest وhashes.
- بناء Universe point-in-time.
- إجراء Unit وIntegration وcausality checks.
- Base backtest للفترات المقررة.
- Walk-forward دون فتح Final Test.
- Stress/Ablation بإعدادات مثبتة.
- فتح Final Test بعد تجميد النسخة وتسجيله.
- توليد جميع التقارير وCSV/Parquet.
- Paper وإعادة تشغيل آمنة مع reconciliation.
كل أمر لاحق يجب أن يذكر working directory والبيئة والإصدار وملف الإعدادات والبيانات والمخرجات وexit code المتوقع. لا أمر LIVE ضمن الإذن الحالي.

108. Known limitations
حجم مرتفع قد يمثل نهاية حركة؛ اختراق 24h قد يتأخر؛ Trailing يعيد أرباحًا ورقية؛ SHORT يتعرض لقفزات وتمويل مختلف؛ الأرباح قد تتركز في اتجاهات قليلة؛ الفلاتر قد تقلل العينة؛ Market impact يتغير مع رأس المال؛ stop ليس ضمان تنفيذ؛ منصة متوقفة أو Mark gap قد يتجاوز الحماية؛ كثرة التجارب تنشئ Overfitting؛ تسمية فرضية اقتصادية لا تثبت السببية من السعر والحجم وحدهما.
مضاعفة أسبوعية ليست توقعًا تصميميًا. عند مخاطرة ثابتة 1% من رأس المال الابتدائي دون تركيب، المضاعفة تحتاج صافي 100 وحدة مخاطرة ابتدائية؛ هذا حساب توضيحي للهدف لا نتيجة Backtest. لا يُرفع خطر النسخة لإجبار هذا الهدف.
الفكرة تستهدف استمرار إعادة التسعير ساعات إلى أيام. المقارنة السابقة فضّلت قابلية الاختبار وبساطة السعر والحجم، ولم تثبت تفوقًا تجريبيًا على Pullback أو Mean Reversion أو Order Flow. Latency أقل حدة من إشارات أجزاء الثانية لكنه يظل تكلفة قابلة للاختبار.

109. Missing historical data limitations
غياب L2 يمنع إثبات السبريد والتعبئة وpartial fills؛ غياب received_at يمنع الادعاء بمعرفة التأخر التاريخي؛ غياب Mark يمنع حسم التصفية؛ غياب شرائح الهامش يمنع دقة سعر التصفية؛ غياب funding ومواعيده لا يعالج بصفر؛ نقص metadata يهدد Universe survivorship؛ تاريخ مصحح لاحقًا يهدد إعادة إنتاج مشاهدات الحي القديمة.
لا تولّد OI أو دفتر أو Funding من OHLCV. لا تحذف فترات غياب البيانات لأنها غير مريحة ثم تعرض نجاحًا بلا coverage report. مجموعة تنفيذ دقيقة تحتاج مصادر وتغطية ومراجعات موثقة، ولا يكفي رابط أرشيف عام. صلاحية نشر نتيجة ناقصة مشروطة بالوسم Preliminary/INCONCLUSIVE لا Verified Edge.

110. UNRESOLVED_DECISIONS
هذا السجل جزء ملزم من التسليم. الخيارات هنا فقط، ولا تتحول إلى defaults في الأقسام السابقة. يجب أن تسجل كل إجابة مع صاحب القرار وتاريخه وأثرها وconfig hash جديد. كل القرارات أدناه OPEN. قرار لا يغير الفلسفة يظل يحتاج تثبيتًا هندسيًا؛ قرار يغير القواعد البحثية يحتاج إصدارًا موثقًا.

UD-01 | Statistical definitions | يؤثر في RVOL وSlippage وFunding وRegime وAcceptance.
غير محسوم: median للعدد الزوجي، std population أم sample، simple أم log لعوائد الدقيقة، quantile interpolation، ومقام downside deviation.
الخيارات: median متوسط الوسطين أو اختيار رتبة محددة؛ std ddof=0 أو ddof=1؛ minute returns simple أو log؛ nearest-rank quantiles أو linear interpolation؛ Sortino downside على كل الأيام مع zeros لغير السالب أو على الأيام السالبة فقط. يجب اختيار تعريف واحد لكل متغير دون تغيير نتائج لاحقًا.

UD-02 | ATR origin and gaps | يؤثر في كل إشارة ووقف.
غير محسوم: نقطة first true_range، بذرة ATR عند تاريخ عقد كامل مقابل warmup مقطوع، وتمييز دقيقة/ساعة بلا تداول عن بيانات مفقودة.
الخيارات: بذرة canonical من بداية تاريخ موثق مع checkpoint دائم أو بذرة من warmup ثابت معلن لكل run؛ gap يوقف الإشارات حتى تعافٍ محدد أو معالجة موثقة لشموع فعلًا خالية من التداول. لا تعبئة سعر مفقود كحقيقة تداول.

UD-03 | Universe security master and stale list | يؤثر في العينة التاريخية.
غير محسوم: المصدر المؤرخ للتصنيف والإدراج/إعادة الإدراج، وتعريف بداية ساعة سماح stale Universe.
الخيارات: سجل منصة مؤرشف أو security master مؤرخ ومدقق؛ حساب السماح من 00:05 موعد التحديث أو من وقت آخر صلاحية معروف. يجب تثبيت كيفية التعامل مع data_revision المتأخر والرمز الذي أعيدت تسميته.

UD-04 | Temporal availability and batch | يؤثر في ترتيب الإشارات والتنفيذ.
غير محسوم: تجميع batch مع وصول غير متزامن، حدود المساواة لـ30/90 seconds، مزامنة clocks، processing/network/ack delay، وحد freshness لمصادر غير Book.
الخيارات: انتظار جميع مدخلات القائمة حتى deadline أو انتظار deadline ثم تقييم المتاح مع كشف الناقص؛ شرط expiry strict أو inclusive؛ replay received timestamps حين تتوفر أو fixed/distribution delays معلنة. تعريف decision_time يظل مبنيًا على المدخلات المتاحة فعلًا.

UD-05 | IOC cap and L2 model | يؤثر في سعر وتعبئة الدخول.
غير محسوم: تحويل VWAP gates إلى worst-price Limit، rounding لذلك limit، أصل Book age، سلامة sequence، تحديث العمق وتأثير أمرنا على إعادة استخدام السيولة.
الخيارات: سقف يشترط أسوأ مستوى ضمن الحدود أو سقف يسمح بمستوى أبعد ما دام VWAP صالحًا؛ عمر event-time أو receive-time مع gate ثان؛ conservation model يخصم استهلاك أوامرنا أو independent small-order replay مع تحذير capacity. طريقة توزيع haircut على المستويات يجب أن تثبت. لا يسمح أي اختيار بمطاردة الإشارة أو ربح من معلومات مستقبلية.

UD-06 | IDs, idempotency, durable state | يؤثر في عدم تكرار الأوامر والمحاسبة.
غير محسوم: serializer/hash للهوية، client ID length، transactions/checkpoints، آجال lookup ومراجعة Fill IDs، وترتيب primary rejection code.
الخيارات: هوية نصية canonical أو hash منها مع mapping محفوظ؛ event journal مع transaction store أو state store transactional يضمن write-ahead intent. تسلسل التحقق وإعادة الاستعلام يحدد قبل إرسال حي.

UD-07 | SPEC_CONFLICT-02 / unfilled cooldown | يؤثر في عدد الفرص.
الطرف الأول: جدول الحالات يرسل ENTRY_PENDING دون تعبئة إلى COOLDOWN.
الطرف الثاني: المؤقت 6h يبدأ full_exit_time؛ IOC غير المنفذ ليس له صفقة خرجت.
الخيارات: استهلاك signal_id والعودة READY مع شرط transition جديد دون 6h؛ أو اعتماد 6h بعد نتيجة عدم التعبئة كقاعدة إضافية معلنة. لم يُعتمد أحدهما.

UD-08 | Protection, exits and rounding | يمنع اكتمال تنفيذ آمن وحتمي.
غير محسوم: مهلة Stop acknowledgement، retries، Market/IOC للخروج، حماية كل جزء دخول وتثبيت VWAP، rounding للTrailing، replace atomicity، والتصرف أثناء cancel/fill race.
الخيارات: أمر خروج Market مخفض أو بروتوكول IOC متتابع بمهلة وتصعيد معلوم؛ Trailing تقريبه باتجاه حماية أشد أو باتجاه أقرب سعر صالح مع عدم التوسيع؛ حماية أول Fill ثم تعديلات معلنة أو حماية مجموع Fill مؤكدة ضمن مهلة محددة. الأرقام التشغيلية لهذه الخيارات غير مختارة. Stop failure يبقى مؤديًا للإغلاق وتعليق المداخل.

UD-09 | Risk solver and post-fill breach | يؤثر في الكمية والحجز.
غير محسوم: خوارزمية البحث عن quantity feasible، convergence tolerance ضمن 5 دورات، سعر تقييم exposure وmargin commitments، احتياطي الرسوم الحرة، حجز خروج جزئي اضطراري، وتجاوز post-fill.
الخيارات: بحث monotonic محافظ محدود أو decrement steps حتمي؛ notional عند Mark أو سعر دخول لأغراض Gate مع تسمية واضحة؛ تقليل مركز تجاوز إلى كمية صالحة أو إغلاقه كاملًا. لا ترفع كمية دون الحد الأدنى ولا تسمح بتجاوز cap كـ silent tolerance.

UD-10 | Liquidation and gap policy | مانع جاهزية جوهري.
غير محسوم: معادلة المنصة بكل شرائحها وmaintenance deductions، settlement chronology، رسوم التصفية، intrabar Mark، تدهور buffer بعد الدخول، وكون gap stress Gate أم تقريرًا.
الخيارات: Adapter دقيق ببيانات تاريخية مثبتة أو نموذج محافظ معلن لا يدعي exact replay؛ gap gate بموازنة خسارة صريحة أو تقرير حساسية فقط. حد خسارة gap لم يحدد. سياسة breach أثناء الحياة تحتاج اختيار تقليل/إغلاق وتوقيتًا صريحًا. يمنع اختراع سعر تصفية من الرافعة وحدها.

UD-11 | SPEC_CONFLICT-03 / costs and funding | مانع تحديد الحجم والتكلفة النهائي.
الطرف الأول: تكلفة RoundTrip كاملة مطلوبة في نسبة 0.25.
الطرف الثاني: expected_entry يتضمن أثر الدخول، ولا تعريف لمرجع تكلفة هذا الدخول، ولا g calibrated ولا fallback fee معتمد.
الخيارات: اختبار تكلفة كامل يشمل arrival-reference shortfall مع إبقائه خارج خصم Loss المكرر؛ أو تعريف gate صراحة كاحتياطي تكاليف إضافية وتوثيق أنه ليس total round-trip. يلزم أيضًا حسم 0.0005 fallback أو تعرفة تاريخية، conversion time للرسوم غير USDT، نموذج stop slippage، missing funding، quantile method، والتعامل عند settlement boundary. لا خيار يعفي من تسجيل التكاليف الفعلية مرة واحدة.

UD-12 | Equal-time event order | يؤثر في الخروج وPnL.
غير محسوم: Fill وClose في الطابع نفسه، عد الإغلاقات بعد الدخول، tie-break إغلاق صفقات، ترتيب funding/day boundary، وكيف يعالج إغلاق مفقود ضمن أول 3/6 إغلاقات.
الخيارات: ترتيب exchange sequence موثوق ثم timestamp أو priority deterministic معلن عند غيابه؛ close عند fill_time يستبعد strict أو يعالج حسب sequence. لا high/low سابق للتعبئة. يجب عدم تجاوز ترتيب الوقائع المؤكدة بتفضيل مربح مصطنع.

UD-13 | Historical coverage and delisting | يؤثر في Universe والتسويات.
غير محسوم: مزود قواعد العقود، تغطية المشطوبين والتصنيف، مراجعات البيانات، سياسة بدء وقف المداخل/الإغلاق بعد إعلان شطب.
الخيارات: أرشيف منصة مؤرخ أو مزود مستقل مدقق؛ إغلاق عند إعلان متاح أو قبل موعد التسوية بهامش وقت معلن. الهامش الزمني غير معتمد. فترات نقص القواعد إما تمنع الادعاء باختبار دقيق أو تدخل سيناريو معلن؛ لا تختفي بلا تقرير.

UD-14 | SPEC_CONFLICT-01 / preliminary execution | مانع حسم Backtest.
الطرف الأول: Book age/spread/depth gates إلزامية للدخول.
الطرف الثاني: الاختبار الأولي OHLCV لا يملك هذه المقاييس ويُسمح به لإسقاط الفكرة.
الخيارات: وضع Preliminary يوسم هذه الفحوص UNVERIFIED ويستعمل proxies معلنة دون ادعاء مطابقة كاملة؛ أو قصر البحث القابل للتنفيذ على الفترات التي تملك Quotes/L2. يلزم أيضًا تحديد intrabar stop/liquidation ambiguity، open-before/after semantics، نموذج fill جزئي أولي أو التصريح بعدم تمثيله، ومراجع خروج 1m أثناء فجوة. لا تنقل stop-first من استراتيجية أخرى على أنه قرار سابق هنا.

UD-15 | Physical schemas and numeric precision | يؤثر في إعادة الإنتاج.
غير محسوم: Decimal precision/scale، timestamp units، CSV delimiter/quote/null/list serialization، Parquet compression/partitioning، schema_version، كامل enums وأعمدة snapshots الإضافية.
الخيارات: decimal strings في CSV مع DECIMAL typed في Parquet أو مخطط fixed-scale متطابق؛ timestamps ISO UTC أو epoch بوحدة موحدة. الدقة وعدد الخانات والوحدة والإصدارات يجب تثبيتها قبل code freeze. لا تغيير منطقي للمعادلات مطلوب لهذا القرار.

UD-16 | Implementation environment and reproducibility | يمنع أوامر تشغيل حقيقية.
غير محسوم: repository وbranch وcode SHA وFreqtrade version والبيئة والمحرك الخارجي والـ CLI وdata/config hash canonicalization.
الخيارات: Freqtrade مع مرجع Event-driven خارجي أو محرك موحد يمر عبر Adapter تشغيل واحد. في الحالتين يلزم إثبات signal parity وsingle order authority. يعتمد hash algorithm وصيغة manifest وأوامر فعلية بعد البناء؛ لا أوامر وهمية في هذا الملف.

UD-17 | Equity, drawdown and resume | يؤثر في إدارة المخاطر.
غير محسوم: حساب مخصص مقابل تخصيص محاسبي، flow adjustment، sample-grid alignment، stale Mark، مرجع قمة الاستعادة، وفصل PAUSED الحسابية عن حالة الرمز.
الخيارات: حساب مخصص بلا تدفقات أثناء run أو NAV unitization للتدفقات الحية؛ حفظ قمة الدخول لحالة reduced-risk أو متابعة قمة السلسلة وفق تعريف معلن؛ resume operational بقرار موثق بعد reconciliation أو فحوص تلقائية محددة لا تشمل hard drawdown. لا يرفع daily reset تعليق 15%.

UD-18 | Validation governance | يؤثر في صدق الاستدلال.
غير محسوم: هل Final Test سبق استعماله، تاريخ التجميد المستقبلي، أحجام الحساب المرجعية، حدود carry/purge للWalk-forward، وأي عينة بالضبط تقاس عليها بوابة 300/100/52.
الخيارات: test محفوظ حقيقي إذا لم يُر أو retrospective موسوم مع future holdout؛ اعتماد 200/1000/10000 كـ runs محددة مع حساب قبول مرجعي أو اختيار حجم واحد مسبقًا. لا اختيار الحجم بعد رؤية النتائج.

UD-19 | Statistical/stress protocols and qualitative gates | يؤثر في القبول.
غير محسوم: نوع Bootstrap وCI والبذور، شدة fees-only، مواضع outages، ترتيب إزالة أفضل 5، تعريف أيام التعطل "معظم"، وحدود التركّز والهشاشة.
الخيارات: moving/circular/stationary blocks موثقة وpercentile/basic CI؛ حذف مساهمة أفضل 5 كتشخيص حسابي أو replay بدونها مع كشف اختلاف التخصيص؛ outage جدول ثابت أو سحب مسجل قبل الاختبار. الحدود غير الرقمية تقبل مراجعة موثقة أو تتحول إلى حدود رقمية مسبقة قبل Final Test. لا أرقام مخترعة هنا.

UD-20 | Diagnostic sampling | يؤثر في تحليل الأنظمة والشرائح.
غير محسوم: سعر مرجع BTC وتواتر تشخيص 30-day return والتقلب، تاريخ سنة المئينات وإدراج النقطة الحالية، شرائح السيولة والتكلفة.
الخيارات: حساب ساعة بساعة على آخر close متاح أو snapshot يومي ثابت؛ مرجع percentile يستبعد الحالية وفق نافذة محددة ويثبت قبل التشغيل؛ شرائح ثابتة أو quantiles سابقة فقط. هذه تسميات تقارير ولا تتحول إلى فلاتر Alpha بلا إصدار جديد.

SPEC_CONFLICT REGISTER
SPEC_CONFLICT-01: mandatory book gates مقابل اختبار أولي بلا Book. مرجعه UD-14.
SPEC_CONFLICT-02: unfilled IOC إلى COOLDOWN مقابل بدء Cooldown فقط عند full exit. مرجعه UD-07.
SPEC_CONFLICT-03: تسمية التكلفة RoundTrip الكاملة مقابل مرجع دخول غير محدد وأثر مضمّن في سعر التنفيذ. مرجعه UD-11.
الفارق بين hard pause عند 15% ورفض drawdown فوق 20% ليس تعارضًا لازمًا: الأول Trigger للخروج والثاني gate لنتيجة قد تتجاوز Trigger بسبب gap/latency. لا تُخفض 20% أو ترفع 15% لتوحيدهما بصمت.

FUTURE_RESEARCH_ONLY
إضافات منفصلة بعد اختبار النسخة: OI، Taker، Compression، تصنيف Regime للدخول، ترتيب القوة النسبية، وأي partial exit أو breakeven. ليست معتمدة في PVB-24 v1.0. تدرس بعينات مشتركة سببية وتصميم Ablation مسجل، لا تكديس مؤشرات بعد رؤية Final Test. إذا ثبت أن Price-only أبسط أفضل، يطرح بإصدار مستقل لا بتعديل v1.0 في تقريرها.

SOURCE CONTEXT
المرجع المباشر للقواعد هو آخر مواصفة PVB-24 المفصلة في هذه المحادثة وطلب الملف المرفق. لم يجر في إعداد هذا الملف Backtest أو تدقيق API حي أو تأكيد توفر البيانات. الروابط التالية هي مراجع البحث المذكورة سابقًا وليست إثباتًا لربحية التصميم:
- https://github.com/binance/binance-public-data
- https://www.freqtrade.io/en/stable/backtesting/
- https://www.freqtrade.io/en/stable/leverage/
- https://www.freqtrade.io/en/stable/lookahead-analysis/
- https://arxiv.org/abs/1011.6402
- https://arxiv.org/abs/2607.27070
- https://arxiv.org/abs/2602.11708
تثبت نسخ الوثائق المستخدمة في التنفيذ لاحقًا، ولا تُفترض ثبات الواجهات عبر الزمن.

IMPLEMENTATION HANDOFF CHECKLIST
- هل كل المعادلات مكتملة؟ NO. معادلات Alpha معروفة؛ تفاصيل std/quantile والتكلفة النهائية والتصفية وأحداث التنفيذ ما زالت UD.
- هل توجد أي قيم غير محسومة؟ YES. UD-01 إلى UD-20.
- هل توجد أي SPEC_CONFLICT؟ YES. SPEC_CONFLICT-01 وSPEC_CONFLICT-02 وSPEC_CONFLICT-03.
- هل LONG وSHORT معرفان كاملًا؟ YES للمنطق Boolean والقناة والحدود؛ جاهزية مدخلاتهما وتوقيت batch تتوقف على UD.
- هل توقيت البيانات معرف؟ PARTIAL. الحقول والسببية والمواعيد معروفة؛ ties وbatch وlatency التفصيلي غير محسومة.
- هل Entry معرف؟ PARTIAL. IOC وVWAP وحدود القناة معروفة؛ cap rounding وL2/proxy protocol غير محسومة.
- هل Stop معرف؟ YES للمعادلة والمرجع والتقريب الأولي؛ حماية أجزاء Fill وتأكيدها UD.
- هل Trailing معرف؟ PARTIAL. التفعيل 2R والصيغة 3ATR وcloses معروفة؛ rounding وأوقات التعديل UD.
- هل Position Sizing معرف؟ PARTIAL. معادلة Loss وحدود المحفظة معروفة؛ cost reserve وsolver/overrun policy UD.
- هل Liquidation rules معرفة؟ PARTIAL. buffer 3R وترتيب الأسعار معروفان؛ exchange liquidation model والشرائح UD.
- هل Funding accounting معرف؟ YES للمبدأ الخطي وعدم التكرار؛ settlement ties والتحويل والتغطية UD.
- هل Backtest model معرف؟ PARTIAL. النماذج والمحددات مذكورة؛ intrabar وغياب Book وtiming UD.
- هل State Machine معرفة؟ PARTIAL. الحالات والأساس موجودان؛ unfilled cooldown والفصل العالمي UD.
- هل Rejection codes معرفة؟ YES للقائمة الأساسية؛ الأولوية والربط الكامل UD.
- هل Unit Tests معرفة؟ YES لنطاق التغطية؛ السلوك المنتظر للبنود المفتوحة لا يثبت قبل حسمها.
- هل كل الملفات المطلوبة معرفة؟ YES منطقيًا للجداول؛ المخططات المادية والـ CLI UD.

```text
READY_FOR_IMPLEMENTATION = NO
```
الوحدة: حالة وثيقة نصية، لا نتيجة تداول.

النقاط الناقصة التي تمنع الجاهزية الكاملة:
1. UD-01: تعريفات الإحصاء الدقيقة.
2. UD-02: بذرة ATR وتاريخها ومعالجة gaps.
3. UD-03: سجل Universe والإدراج والتصنيف وحد stale list.
4. UD-04: batch وتوقيت الإتاحة والمهل والتأخير.
5. UD-05: حد IOC وrounding وعمر/محاكاة L2.
6. UD-06: هويات الأوامر والديمومة وidempotency.
7. UD-07: حسم تبريد عدم التعبئة.
8. UD-08: مهلات الحماية والخروج وتعديل Trailing والتعبئات الجزئية.
9. UD-09: solver وحدود التقارب وتقييم التعرض وتجاوزات post-fill.
10. UD-10: معادلة التصفية التاريخية وسياسة gap والـ buffer أثناء المركز.
11. UD-11: تعريف RoundTrip cost واحتياطي الانزلاق وتعرفة fallback وتحويل الرسوم وحدود Funding.
12. UD-12: ترتيب الأحداث المتزامنة وعد الإغلاقات.
13. UD-13: قواعد العقود والتغطية وسياسة الشطب.
14. UD-14: بروتوكول الاختبار الأولي وintrabar ambiguity.
15. UD-15: أنواع الملفات ودقة Decimal والزمن والـ enums النهائية.
16. UD-16: بيئة التنفيذ وإصداراتها والـ CLI والـ hashes الفعلية.
17. UD-17: Equity المعدلة بالتدفقات والقمم وPause/Resume.
18. UD-18: نزاهة holdout وتجميد البحث وحدود Walk-forward وأحجام الحساب المرجعية.
19. UD-19: البروتوكول الإحصائي والضغوط والبوابات النوعية.
20. UD-20: عينات Regime وشرائح التحليل.

END OF SPECIFICATION
