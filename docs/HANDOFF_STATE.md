# Handoff — Milestone 8E (open account reconciliation)

- Repository: novacorestudios/Pvp-24; branch build/pvb24-v1.
- Exact current HEAD: read the Git branch ref; main remains initialization only.
- Milestone 0 remote HEAD: f1d9ece4d4cc14d09adfe715d043ee58de437ad8.
- Milestone 0 CI: https://github.com/novacorestudios/Pvp-24/actions/runs/35422954155 — SUCCESS.
- Public-disclosure authorization: user explicitly approved publishing these files and will change visibility later. Do not request this approval again.
- Milestone 1: official Freqtrade 2026.8 / 9f10e357a93c1dcf10c2a2b367659214d89c073e installed; repeat locked install and offline dry-run config smoke passed.
- Local tests: 199 passed; Ruff lint/format passed. CI for this commit: check GitHub Actions after publication.
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
- Next: verify Milestone 8E CI, then implement the causal reference event loop and replay integration.
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
