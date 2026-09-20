# Paper readiness

NOT READY. LIVE remains disabled. No operational trading process or external order has been started.

The pinned Freqtrade strategy loads, shared-core signal/intent parity passes, and the PAPER dispatch boundary has synthetic tests for write-ahead recovery, owned protection/exit/cancel tickets a single journal authority, and normalized owned fill/terminal/cancellation evidence with atomic account settlement. The current bridge still refuses operational dispatch.

A concrete durable PRELIMINARY L2 backend now models entry, LAST protective stops, reduce-only market exits and cancellation, with recoverable fills/refusals and pending residuals. Remaining gates include funding/collateral/liquidation execution modeling, durable feed/cursor/dispatch orchestration, full process integration, source-backed market/funding/rules coverage and execution-model qualification. Native Freqtrade dry-run does not preserve the required IOC/reduce-only semantics and is not used as a substitute.

Current safe reproduction commands are in REPRODUCE.md. They run offline configuration/parity and synthetic integration checks without API keys. These results are not historical backtest performance or the required 90-day paper record.
