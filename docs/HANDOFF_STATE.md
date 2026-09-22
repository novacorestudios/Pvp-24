# Handoff — Post-audit remediation checkpoint

## Current authoritative checkpoint — 2026-09-22

- Repository: `novacorestudios/Pvp-24`; work branch: `build/pvb24-v1`.
- Audit-remediation implementation checkpoint before this F9 documentation sync:
  `527a15c3d89c966686fe51fec38a3b243bbee674`.
- Last implementation CI before this documentation sync: **PVB-24 CI #283 — SUCCESS**.
- CI #283 passed **743 tests**, Ruff format/check, provenance, reference smoke,
  Freqtrade smoke, Freqtrade parity and framework parity.
- Reference smoke remained non-trading:
  `orders_sent_to_exchange=0`, `paper_ready=false`.
- Baseline provenance remained unchanged:
  `source_sha256=098a3ca390bce81d506bdec011fc3a936ecbb793f46c2f117f337998bfc1c5d8`,
  `config_hash=6d267edbcde56081012bc7b93d46f2c7f345aceb0e3bc769095ba53ef00b5be7`,
  `live_enabled=false`.
- Final Test remains **LOCKED**.
- Historical performance remains **BLOCKED** by the fail-closed readiness gate.
- Operational readiness remains **false**.
- PAPER remains **NOT READY**.
- LIVE remains **DISABLED**.
- No strategy/Alpha/threshold/sizing/leverage/risk/entry/exit semantics were changed
  by the engineering-audit remediation.

### Engineering audit remediation status

The independent Production-grade audit remediation is complete. The authoritative
status record is `docs/PVB24_ENGINEERING_AUDIT_REMEDIATION.md`.

Closed findings:

- F1 — cutoff coverage / generalized cutoff scope.
- F2 — connector pseudo-symbol parsing such as `ANDUSDT`.
- F3 — timezone causality and explicit UTC requirements.
- F4 — lifecycle report/fact symbol binding.
- F5 — conflicting delisting revisions and causal postponement semantics.
- F6 — durable, content-addressed M11T evidence preservation and restore.
- F7 — per-source point-in-time availability and reconciliation availability.
- F8 — regression/invariant test coverage.
- F9 — handoff/readiness documentation synchronization.
- F10 — evidence qualification bound to successful same-SHA CI plus payload hashes.

The post-F6 durable replay is also pinned as a recurring regression gate. The
bounded recovery and historical-metadata compilation remain byte-identical to
their audited baselines even though the current parser exposes diagnostic
qualification differences in retained raw sources. Those diagnostic differences
are not silently promoted into downstream evidence.

### Current evidence controls

- Durable bundle SHA-256:
  `9bef3d0684b525c8ee0db0e9d1c4f27fcddea5f6b53c1ea1911f3bbee150f5e4`.
- Durable manifest SHA-256:
  `e14af7876f770f9d20e3896a9d0df73bdbe26b3cb494c59e51e221f7a713349d`.
- M11X bounded recovery output SHA-256:
  `aedcd648151c26968268c1580b7c6bf10284a1d1774c86bc21074f7fe697943d`.
- M11V historical metadata output SHA-256:
  `8130ae8d57cb60747daaef379a1713a990937d499a86360c920d0584a7e20252`.
- Security Master audit schema is
  `PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V5` with
  `PER_SOURCE_POINT_IN_TIME_V1` availability semantics.
- Evidence workflows are post-CI dispatch only and require an explicit
  `source_sha`; evidence is qualified only when the same SHA has a successful
  `PVB-24 CI` run with both `governance` and `freqtrade-smoke` successful
  from that same run. Payload inventories are SHA-256 sealed before upload.

### Readiness remains deliberately fail-closed

Audit remediation closure does **not** promote historical-data capabilities to
COMPLETE. The frozen pre-Final readiness matrix still has all eleven mandatory
capabilities at `PARTIAL`, including historical universe, security master,
contract rules, lifecycle, LAST/Mark coverage, funding pricing/schedule/reserve,
and liquidation rules.

Do not run or publish a strategy performance evaluation until
`python scripts/check_historical_evaluation_readiness.py` exits successfully.
Do not unlock the Final Test or enable LIVE as part of ordinary development work.

### Next engineering handoff

The audit-remediation lane is complete. Resume normal project development from the
current branch HEAD, while preserving the existing fail-closed readiness,
Final-Test lock, provenance controls, and evidence qualification policy.

---

## Legacy milestone history retained below

- Repository: novacorestudios/Pvp-24; branch build/pvb24-v1.
- Exact current HEAD: read the Git branch ref; main remains initialization only.
- Milestone 0 remote HEAD: f1d9ece4d4cc14d09adfe715d043ee58de437ad8.
- Milestone 0 CI: https://github.com/novacorestudios/Pvp-24/actions/runs/35422954155 — SUCCESS.
- Public-disclosure authorization: user explicitly approved publishing these files and will change visibility later. Do not request this approval again.
- Milestone 1: official Freqtrade 2026.8 / 9f10e357a93c1dcf10c2a2b367659214d89c073e installed; repeat locked install and offline dry-run config smoke passed.
- M11S corrected code checkpoint: 8351633d5f14238642c0e3cbe64a039cc2fad16d. Actions 35633773768 — SUCCESS: Ruff format/check, 629 tests, provenance, reference smoke, Freqtrade smoke, parity and framework parity all passed.
- M11S corrected source-evidence workflow: Actions 35633393635 — SUCCESS on 9df9dc626eb98258c7d89ae231929bb608355099. The later commits through 8351633d5f14238642c0e3cbe64a039cc2fad16d are formatting/test-lint-only; production lifecycle semantics are unchanged. Catalog 48/161 anchors, pinned inventory, qualification V2 and lifecycle reconciliation V2 all succeeded.
- M11T code checkpoint: c7a1fe4d3b51ad0ac0e0f94ae76da9c647029ddb. Actions 35637293211 — SUCCESS: Ruff format/check, 633 tests, provenance, reference smoke, Freqtrade smoke/parity/framework parity all passed.
- M11T source-evidence workflow: Actions 35636682664 — SUCCESS on c51a89b15030a5d5996a6fc3877969bcf112d757. Catalog 48 listing-delay discovery now captures the retained DOT postponement article causally; later commits through c7a1fe4d3b51ad0ac0e0f94ae76da9c647029ddb are test-formatting-only.
- M11U funding code checkpoint: 6450091cb26ef80365740690a64be2ae83b3ea37. Actions 35640860553 — SUCCESS: Ruff format/lint, 638 tests, provenance, reference smoke and Freqtrade smoke/parity/framework parity all passed. M11U hardens settlement-Mark diagnostics and adds a fail-closed funding schedule audit; no strategy/risk/execution/config file changed.
- M11U retained 11G evidence audit: PVB24-source-evidence-11G.zip SHA-256 85206d50a6148bbbafb285c69eece7fa1a1c8ebd592cb485bdb5448286f7baeb; all 508 manifest files reverified with zero byte/hash/size failures. The selected 67-month BTCUSDT funding evidence has 6024 archive settlement rows across 66 matched months, with 2019-12 archive unavailable. Across 6023 adjacent archive pairs, 2486 equal the declared 8h duration exactly and 3537 preserve millisecond jitter; differences range -45ms to +47ms, with zero pairs large enough for another whole declared interval and no timestamp rounding. This corroborates an ex-post event index only: causal_next_settlement_time_verified=false, funding_schedule_complete=false, no FundingCoverage emitted and funding_reserve_coverage_qualified=false. The existing 4291 missing source-associated settlement Marks remain missing; OHLC current-open and previous-close are diagnostics only and never settlement-price substitutes. Report docs/data/11u-funding-schedule-audit.json SHA-256 327861b288769e17854aff80f10ce641124de2cbf074cab21999f8b63e855541; audit hash e774d7d89ff81042cb89ad338c3816122b34d25fdcbafb246c5a528bcd68cc9c. Final Test LOCKED; operational_ready=false; PAPER NOT READY; LIVE DISABLED.
- M11V historical metadata evidence: code checkpoint c26760873b0393d49a62639579206eef326072b5; CI 35647746659 (#143) SUCCESS. Evidence workflow 35648265777 (#4) SUCCESS restored exact M11T qualification/lifecycle pins and the committed M11F tick report, then produced docs/data/11v-historical-metadata-evidence.json with SHA-256 8130ae8d57cb60747daaef379a1713a990937d499a86360c920d0584a7e20252 and evidence hash 4794c5f0fb40ef343523d56744c6e7a9e9fa7b24fcdd22879df7f7af078bc26d. Result: 15 consistent preliminary listing candidates, 7 UNKNOWN listings retained, 11 delisting events, 10 USDT tick-field events, 0 full Security rows and 0 full ContractRules rows. classification/security change-stream/contract-rule/liquidation-tier completeness all remain false; historical_universe_complete=false. No strategy/risk/execution/config change; Final Test LOCKED; operational_ready=false; PAPER NOT READY; LIVE DISABLED.
- M11W historical liquidation evidence: source-probe Actions 35650220174 (#4) SUCCESS with artifact digest 3d3c21c8dd0c2544fa91c7d9b36353b64b116a8e413ba675de816b2ac00961e0. Three pinned official Binance margin-tier revisions cover 13 USD-M symbols: 2 changes were announced before effective time and 1 was published after effective time and remains retrospective only. Position-cohort policy is source-dependent: two revisions preserve pre-update positions on the old rules, one explicitly affects existing positions. Compiler checkpoint bd664c3bdcae46a79191132337cacb2ed9a3c335; CI 35651486792 (#155) SUCCESS. Evidence workflow 35651999817 (#2) SUCCESS; docs/data/11w-historical-liquidation-evidence.json SHA-256 85f37fc75f3b489844acdffa91d41625333ffdcce53a6f92daa8ec4899dab6ae, Git blob ae118a1042cfe888d5119e1c3e176ae9edabd9eb, evidence hash 304cdc5a9d65a3ad86be4001babd0ad166b2469431b95e3d8cd095c99768e5f2, artifact digest 48cbd9c9c907a8db8411b4af5700744d2010f0cad6ae2672dfefeae8346da2a5. maintenance_amounts_complete=false, maintenance_deductions_complete=false, exchange_liquidation_value_validation_complete=false, historical_liquidation_rules_complete=false, liquidation_validated=false and contract_rules_emitted=0. LIQUIDATION_RULES readiness remains PARTIAL. No strategy/risk/execution/config change; Final Test LOCKED; operational_ready=false; PAPER NOT READY; LIVE DISABLED.
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
- Milestone 10D: 2b270a8bc9f96e31cdb943aabf8e0069aef072ff; CI https://github.com/novacorestudios/Pvp-24/actions/runs/35490438954 — SUCCESS.
- Milestone 10E: f4330f7a704b6ec0e1afb9e177b8f8b86bb31cf0; CI https://github.com/novacorestudios/Pvp-24/actions/runs/35490911580 — SUCCESS.
- Milestone 10F: 71afee0716bb3b2f06a1db5f9c4864995baeb5ca; CI https://github.com/novacorestudios/Pvp-24/actions/runs/35503322520 — SUCCESS.
- Milestone 10G: 731162abd255aaada44b6f0d9b2330c41d496447; CI https://github.com/novacorestudios/Pvp-24/actions/runs/35503650811 — SUCCESS.
- Milestone 10H: e20723687ccd1aea1848f4fcd72300707fa7e1b8; CI https://github.com/novacorestudios/Pvp-24/actions/runs/35517866023 — SUCCESS.
- Milestone 10I: 5080133a555c44c6f8da09c07953c0b95aee24e1; CI https://github.com/novacorestudios/Pvp-24/actions/runs/35518378324 — SUCCESS.
- Milestone 10J: b382b70089585f1f6eec806fa723c0970b613e64; CI https://github.com/novacorestudios/Pvp-24/actions/runs/35518785512 — SUCCESS.
- Milestone 10K: 56ec5a22344802ad7cba82a4e2c1c853657333ea; CI https://github.com/novacorestudios/Pvp-24/actions/runs/35519333976 — SUCCESS.
- Milestone 11A: cd889fbb2fe01ac45aa0606f777f428681487c90; CI https://github.com/novacorestudios/Pvp-24/actions/runs/35520448889 — SUCCESS.
- Milestone 11B: 3e8121ee2f18ae25b428bc2a6e565f0e527de1d2; CI https://github.com/novacorestudios/Pvp-24/actions/runs/35520817197 — SUCCESS.
- Milestone 11C: 1924c82e015e984516a7b3616a51cde4ffc2acad; CI https://github.com/novacorestudios/Pvp-24/actions/runs/35535965582 — SUCCESS.
- Milestone 11D: 2fff5d3d96a750d2c381f3ebde46c8c4a0feb5b8; CI https://github.com/novacorestudios/Pvp-24/actions/runs/35536525095 — SUCCESS.
- Milestone 11E: 75efc038d8478862de32f663dc5e2e5646cff8e8; CI https://github.com/novacorestudios/Pvp-24/actions/runs/35562083086 — SUCCESS.
- Milestone 11F: e1b226bf29d27a3c671a766805bc4e02458128fa; CI https://github.com/novacorestudios/Pvp-24/actions/runs/35562758298 — SUCCESS.
- Milestone 11G: 24b27298a2efd467e12fa4d1c6a5c8b763280da9; CI 35585717177 — SUCCESS.
- Milestone 11H: a4ced999e35b5deeaea69050f177f9216ab8a662; CI 35587289088 — SUCCESS.
- Milestone 11I final: a5e7cdaa838846a2ba9099924ea5a2340ea26d5f; CI 35593905942 — SUCCESS.
- Milestone 11J final: 8fd34b0c80f5372b60da3ada403588da9b9032ab; CI 35595263337 — SUCCESS.
- Milestone 11K final: 8f9092f2880c7f202bcd4b4d5b58a987a80eda2a; CI 35598476129 — SUCCESS.
- Milestone 11L implementation: 74aa52ed8a2cef39041272f3e7909ee494fd9ed0; CI 35599685386 — SUCCESS.
- Milestone 11L documentation checkpoint: 88b8b3b6f7a6781a51aa5f5635e0525200151d1b; CI 35599961699 — SUCCESS.
- Milestone 11M implementation: 435eaef94db9bc637242712bfa27701739a5fa17; CI 35601347834 — SUCCESS.
- Milestone 11M documentation checkpoint: 2a8707a05d67044f6794cb9a04309e0fd2731110; CI 35601621863 — SUCCESS.
- Milestone 11N implementation final: 0966ffc55948b4e31a494090ac4185752acb4ee5; CI 35603211675 — SUCCESS.
- Milestone 11N documentation checkpoint: 9c8a6d9cd2f0544e3b5843c2ee1bd2104b9e1301; CI 35603602858 — SUCCESS.
- Milestone 11O implementation final: b1911842a8f6950efbc0fba45e023c458464bf55; CI 35606070751 — SUCCESS.
- M11Q/M11R/M11S/M11T announcement/lifecycle evidence: replay-bound safe anchors and catalog slices were acquired for catalogs 48/161 without crossing Final. M11T reviewed the same 680 catalog rows and selected 148 candidates after adding listing-delay/revision discovery. Qualification V3 fetched all 148 official detail responses with zero source-fetch failures: 28 QUALIFIED_PRELIMINARY and 120 SEMANTIC_UNQUALIFIED. Qualification report SHA-256: ed5539a48c6fca0fca16823bfd4dfd60ad3048c57716635adbb5d04d4b5ddd3a; artifact digest sha256:95095899140c1fdfa38db7f171fe7ba5ad4c1d655fe8915d696d42f0c55b7647. The additional qualified record is the retained DOTUSDT listing postponement from 2020-08-20 07:45:59.089 UTC, revising the scheduled launch from 2020-08-20 07:00 to 2020-08-22 07:00. Because that revision became available after the original event, it is retained as one late_revision and does not retroactively erase the old UNKNOWN boundary. Lifecycle reconciliation V3 produced 35 qualified facts, 33 effective records, 2 causal supersessions, 1 late revision, and 66 checksum-verified daily LAST 1m probes with zero source failures: 26 CONSISTENT_EVENT_BOUNDARY_ONLY, 7 UNKNOWN, 0 CONTRADICTED_BY_ARCHIVE_ACTIVITY. The revised DOT 2020-08-22 boundary is consistent with trading beginning exactly at 07:00. The seven original UNKNOWNs remain explicit: WAVES +1m, SNX +2m, original DOT archive unavailable, STORJ +3m, BLZ +2m, NEAR +60m, MATIC +1m, with prior-day objects unavailable and no arbitrary tolerance invented. Reconciliation report SHA-256: 2c935625dffef3a949b7b30c4dfb55ca75b6b78c70771958d710c6925a0253bd; artifact digest sha256:4d8cbb1a7e69acc9ae0ba2fd9e34ae22add956643b847125d853ac9869343021. historical_lifecycle_verified=false and security/universe completeness remain false. Next: funding evidence, including 4,291 missing BTCUSDT funding-settlement Marks plus funding schedule/reserve/eligibility. Final Test LOCKED; operational_ready=false; PAPER NOT READY; LIVE DISABLED.
- Code: immutable Fill/Side types, precision-34 Decimal helpers, canonical IDs, SQLite WAL events/snapshots/write-ahead intents, fail-closed paper guard. Causal Timing/Candle/Mark/rule/security models, as-of revision selection, 30-day gap warmup, deterministic historical Top-20 and stale-universe grace implemented. Streaming Wilder ATR, channel/RVOL, exact long/short transitions, restartable indicator checkpoints, cooldown/status gates and timed simultaneous batch ranking implemented. Risk foundations now include rounded protective-stop costs, separate arrival shortfall gate, causal funding reserve with explicit coverage, immutable open/pending portfolio reservations and proportional confirmed-exit release. Descending quantity-step sizing, 1..5x minimum feasible leverage, isolated tier-consistent liquidation reconstruction, reduce-only post-fill action interface and transactional reservation+ENTRY intent are implemented. Execution market models now include sequence-consistent L2, consumed-depth replay, strict IOC caps and gates, partial sweep previews, and labelled preliminary OHLC proxies. Confirmed-fill protection lifecycle and transactional evidence/state/action-intent persistence now exist. Open-position reconciliation is now implemented; execution adapter and integrated backtest remain unimplemented. M11W adds partial official historical leverage/maintenance-tier evidence, but exchange liquidation-value validation and maintenance amount/cum history are still absent; actual post-fill collateral must come from the adapter, not a hypothetical newly opened smaller position.
- Data: five official BTCUSDT January 2024 archives acquired and SHA-256/CSV verified: LAST/Mark 1m (44640 rows each), LAST/Mark 1h (744 each), raw funding (93). Candle grids complete for this sample only; funding has 28 millisecond interval discrepancies and no schedule attestation. PRELIMINARY availability model; M11V adds partial listing/delisting/tick evidence and M11W adds three pinned historical margin-tier revisions across 13 USD-M symbols, but complete historical rules/security master, maintenance amount/cum history, exchange liquidation validation and qualified historical L2 remain incomplete. See DATA_COVERAGE.md and data/11a-source-manifest.json. No backtest evidence.
- PAPER: NOT READY. LIVE: DISABLED. No orders sent.
- Original source and baseline config hashes unchanged. See config/manifest.json.
- Deviation: existing repository display capitalization Pvp-24 retained. No alpha changes.
- Post-M11P scope audit: comparison from ca5acbfb6d80d721e58c18462f9d6c02b23f9f5d through 6450091cb26ef80365740690a64be2ae83b3ea37 remains confined to data acquisition/provenance, scripts, tests, docs and workflow files. The M11U delta from 1e6b0091d41640da0c5d3c9bbe66980f8f59b08a through 6450091cb26ef80365740690a64be2ae83b3ea37 changes only settlement/funding audit modules, one audit script and tests. No strategy, risk, execution, baseline config or frozen Alpha threshold file changed.
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


## Official source acquisition (Milestone 11A)

The bounded downloader and strict decoder retain immutable official bytes, sidecars, attempts and exact implementation hashes. Whole-batch validation blocks Final Test before network access. Reconsumption verifies object integrity and decoder identity. Missing/failed archives remain explicit, not zero-volume substitutes. No current exchange metadata is treated as historical proof. FundingArchiveRow preserves raw timestamps and declared intervals without inventing continuous funding coverage. The five-file sample and precise limitations are committed in DATA_COVERAGE.md and DATA_PROVENANCE.md. No strategy performance was calculated.


## Frozen causal source windows (Milestone 11B)

ArchiveDataset requires an explicitly reviewed dataset hash and the frozen config hash, verifies the complete report/attempt selection and rechecks source bytes before consumption. Duplicate/failed/foreign revisions, undeclared months and Final Test windows are rejected. LAST and Mark remain separate; the selected availability model gates every returned candle and exposes missing/not-yet-available intervals. Daily LAST aggregation requires all 24 UTC hours, sums exact Decimal quote volume, propagates the latest constituent availability and hashes only causal constituents. Missing hours cannot become complete daily observations.

The actual 11A sample produced 744 LAST hours, 744 Mark hours and 31 daily LAST observations with no gaps; exact hashes and implementation identity are in data/11b-normalization-summary.json. Quality remains PRELIMINARY and no historical eligibility, funding schedule, strategy performance or operational readiness is inferred. The next source task is historical candidate/security-master and rules coverage; the immutable baseline remains unchanged.


## Official directory inventory (Milestone 11C)

Three reviewed directory roots were enumerated completely: 8 monthly data kinds, 9 daily data kinds and 1018 monthly kline symbol directories across two pages. The four original XML pages and observed metadata are committed under data/11c-catalog-pages and data/11c-source-inventory.json. No price/funding archive objects were read by this inventory and Final Test remains locked. The directory listing is observed now; it is not an as-of historical security master and its names cannot be passed as historical universe membership.

Neither inventoried data-kind root exposes an exchangeInfo/security-master/rule-snapshot directory. This is a scoped source finding, not proof that no other source exists. Current exchangeInfo documents current rules and cannot fill historical gaps. BookTicker/bookDepth names do not establish continuous sequence-consistent executable L2 coverage. Historical metadata, causal funding coverage and six-year evaluation remain outstanding.


## Immediate delisting gate (Milestone 11D)

A causal DelistingNotice now enters AccountReplay as an observation. LifecycleService atomically records source identity, latches a per-symbol entry block and cancels only provably unsent entries. UNKNOWN/ACKNOWLEDGED entry outcomes remain unresolved and receive one owned cancellation request. No risk, cash or actual quantity is released by the notice. SignalService, ranked planning, direct reservations and both entry dispatch boundaries consult the latch, so a cached daily Universe cannot permit an intraday announced delisting. Protective and reduce-only management remain available.

Cancellation identities are shared with global risk pauses to prevent conflicting requests when both causes occur. Duplicate evidence replays its receipt; a changed source revision fails closed. A scheduled future settlement does not prove an actual execution or cashflow. No automatic relisting/unblocking is implemented; new historical lifecycle evidence must be reviewed. Eleven synthetic integration tests cover causality, cached universes, pending/unknown orders, restart, shared cancels, rollback and continued protection/exits. The full pinned offline FreqtradeBot parity smoke passes with unchanged hashes and zero external orders.

Two official pre-Final delisting notices were reviewed and factual annotations retained in data/11d-lifecycle-source-review.json. Displayed publication timezone and original revision availability are not qualified, so these annotations are deliberately not executable historical events and do not fill the missing security master or rule history.


## Official funding-history comparison (Milestone 11E)

A bounded, explicit-month public funding-history adapter now verifies symbol, exact time/rate/Mark fields, rate types and ascending order. Inclusive pagination overlaps its boundary timestamp so a second rate type at the same time cannot be skipped; changed overlapping revisions or stalled/truncated pages remain INCOMPLETE. Source bytes and hashes are retained. Missing Mark and unknown/special rate types cannot silently become regular funding or zero costs. Final Test is rejected before I/O.

The actual BTCUSDT January 2024 REST response has 93 Regular rows, all with positive settlement Mark prices, and matches the archive exactly on every timestamp and rate. No millisecond rounding or nearest-time join was used. Both sources retain the timestamp jitter; continuous funding interval/schedule qualification remains unresolved. Raw API evidence and the exact comparison are committed in data/11e-funding-pages and data/11e-funding-comparison.json. No ledger payment, position eligibility, full historical universe or performance result is inferred.


## Pinned historical announcement metadata (Milestone 11F)

The official public CMS endpoint supplies integer-millisecond publishDate, resolving the prior displayed-timezone ambiguity for the two reviewed delisting notices. Three explicitly reviewed pre-Final articles were acquired with raw-byte/body hashes and separately reviewed fact hashes: five USDT perpetual delistings and twelve USD-M tick changes. The published coverage report retains all twelve tick rows, including two USDC-quoted contracts; it does not infer eligibility or fill unreported fields. See data/11f-announcement-review.json and data/11f-announcement-coverage.json.

The adapter revalidates retained bytes and the pinned decoder/report before producing lifecycle events. It uses the frozen +2-second PRELIMINARY availability model after the source publication or a known later update, never after an earlier timestamp when a later update is known. lastUpdateTime=0 is UNKNOWN, not evidence that the current body is the original published revision. Original revision and historical receipt remain unverified; these events cannot enter VERIFIED replay. Future articles do not enter earlier event batches. Current related-article recommendations cannot change the selected article's semantic revision. Body/fact changes require explicit re-review.

Five actual-source DelistingNotice events were generated with exact publication milliseconds; event hash 0904a9bdc632a9682338fd1db1ea7e0e1d798ea195afe39428aab33b5a31b50c. The existing shared lifecycle gate was exercised with synthetic account fixtures for availability, idempotence and restart. No actual orders, fills, funding or performance were generated. Tick deltas deliberately cannot become full ContractRules; listing/classification/contract-size/quantity/notional/maintenance-tier history and complete announcement coverage are still missing.

441 tests pass with Ruff/provenance, including 17 new source/clock/revision/holdout/integration cases. The acquired source selection hash is a65da1c1b329ed60c8dfc1ef726299874859ee2403cbeb4998c733a8a9be6195. Raw CMS responses are retained under data/announcements-11f/objects; public Git contains factual extracts and hashes, not article bodies. A repeat acquisition may change current recommendations/raw response hash; it cannot silently change the reviewed body or facts. Final remains LOCKED; operational_ready=false; LIVE DISABLED.


## Pre-Final Funding source coverage (Milestone 11G)

An explicit BTCUSDT selection covers December 2019 warmup and every Development/Validation month from January 2020 through June 2025. All 67 requested periods were audited; 66 monthly archives (6024 rows) match official REST timestamps/rates exactly. REST supplies 6117 Regular rows across all 67 months. December 2019 archive sidecar returns HTTP 404; its 93 REST records remain present without a corroborating archive. The audit therefore exits 2 with an explicit incomplete comparison result, not a hidden omitted month or failed software test.

Settlement Mark prices are present in 1826 REST records and missing in 4291. The first available Mark is 2023-10-31 08:00 UTC; the last missing Mark is 2023-10-31 00:00:00.001 UTC. Only November 2023 through June 2025 have complete monthly Mark fields. There are 3503 within-month differences between consecutive calc_time timestamps and archive-declared funding intervals. These were preserved, not rounded, stitched or converted into a complete calendar. Cross-month continuity, historical original availability and position eligibility remain unqualified. No FundingCoverage, ledger payment or strategy performance was generated.

The page-chain reader revalidates source bytes, exact cursors, inclusive overlap, a final short page, decoder identity and derived field coverage. The batch writer preserves every requested month in immutable checkpoints. After the prior usage interruption, the pinned 48-month checkpoint was verified and reused; only the remaining 19 periods were downloaded. Resume cannot silently choose a latest source revision, change the requested range/config or retry recorded unavailable sources.

Final source summary: data/funding-11g/summaries/c6b722671ce87fe68afd9ab3b261e9e7616cfb06ffe0e17114ce284d86f90920.json. Source-selection data hash: 7cede73083b59738ce753df2efbac6fd6ffed1e3fad03d9613eece00197a94d4. Committed reports: data/11g-funding-source-coverage.json and data/11g-funding-qualification.json. 463 tests pass with Ruff/provenance, including 22 new integrity/coverage/resume tests.

A reviewed alternative metadata endpoint returned HTTP 401, requiring a pro/business subscription. Its documented contract-multiplier changes are complete, but other historical fields are best-effort; collection availability is not listing time and full maintenance-tier coverage is not established. This is an unqualified potential partial source, not a purchase recommendation or a solution to all historical gaps. Details and primary documentation URL are in data/11g-metadata-source-review.json. No subscription or authenticated access was attempted.

All 508 acquired evidence files for 11A/11E/11F/11G are retained in the user-owned PVB24-source-evidence-11G.zip recovery bundle (4607372 bytes), SHA-256 85206d50a6148bbbafb285c69eece7fa1a1c8ebd592cb485bdb5448286f7baeb. This preserves original archive ZIPs/checksums, REST pages, announcement bodies and acquisition/report identities across workspace loss. The Git repository contains code and factual provenance; see SOURCE_EVIDENCE_RECOVERY.md for exact recovery. Raw announcement bodies are not published in Git. Final remains LOCKED; operational_ready=false; LIVE DISABLED.


## Settlement Mark archive qualification (Milestone 11H)

Offline audit revalidates the 67 pinned funding REST reports/pages without downloading them again. Every missing settlement is retained at its exact integer epoch millisecond, grouped by symbol/month with source report and data hashes, plus first/last timestamps. BTCUSDT has 4291 missing observations from 2019-12-01T00:00:00.000000Z through 2023-10-31T00:00:00.001000Z: 2063 minute-aligned and 2228 nonaligned; 1826 associated REST Marks remain present.

One new official October 2023 Mark 1m archive was acquired and checksum-verified (44640 bars); January 2024's existing archive was reused. October has 83 exact open-time matches among 93 funding rows; January has 78. All matched bars become available later than funding-time +2s under the frozen completed-bar model. Of January's 78 exact-time matches, 61 open prices equal the associated funding Mark and 17 differ. October's two known Marks equal the opens, which does not prove missing settlement prices. No nearest timestamp, rounding, interpolation, close substitution, payment, schedule or eligibility was created. Zero missing prices were filled. Downloading the remaining Mark months would not resolve this source-schema/association failure.

See docs/SETTLEMENT_MARK_REVIEW.md and docs/data/11h-mark-source-manifest.json. The new audit module/CLI refuses tampered source pages, changed selection hashes, duplicate months/samples and Final requests; source agreement never promotes timing or readiness. Tests are synthetic qualification checks; the committed report is actual source evidence. Historical rule search found no complete official snapshot source in the reviewed archive roots/endpoints; that is a scoped finding, not a claim that no source exists anywhere. Continue independent snapshot ingestion work.


## Fail-closed historical metadata snapshot qualification (Milestone 11I)

A new offline historical-metadata path accepts only caller-pinned, content-addressed Binance USD-M exchangeInfo captures with explicit observed_at, available_at and source/revision identity. Reconsumption hashes both the selection and every retained raw JSON object. An effective_from earlier than observation is rejected unless independently marked as historically verified, and all Final Test timestamps remain blocked before normalization.

The parser extracts only fields actually present in the retained source: onboard/trading start, contract status/type, quote asset, PRICE_FILTER tick size, LOT_SIZE quantity bounds/step, minimum notional and advertised IOC support. Duplicate symbol/filter evidence fails closed. Point-in-time selection is causal: a later revision cannot enter an earlier decision.

exchangeInfo is not promoted into a complete historical rule/security master. Classification stays UNKNOWN and historical_verified=false; contract-size semantics, historical maintenance/leverage tiers, LAST-stop capability and change-stream completeness remain explicit gaps. Qualification remains PRELIMINARY with security_history_complete=false, contract_rule_history_complete=false, liquidation_tiers_complete=false and operational_ready=false. The implementation and CLI are documented in docs/HISTORICAL_METADATA_SNAPSHOTS.md.

Eighteen new tests cover source hashing, causal availability, revision leakage, retroactive-time rejection, holdout locking, missing-field gaps and ambiguity. Full CI passes 492 tests with Ruff, provenance, reference smoke and the pinned Freqtrade lifecycle smoke. No external orders were sent and no strategy Alpha/risk/config value changed.


## Legacy Binance listing evidence path (Milestone 11J)

The reviewed announcement adapter now accepts either modern 32-hex CMS article codes or the 12-digit numeric identifiers used by early Binance Futures support announcements. A new LISTING parser is intentionally narrow: one explicit Binance Futures USDT perpetual symbol, one explicit UTC launch time and one announced maximum leverage. It emits only symbol, launch_at, max_leverage, contract_type=PERPETUAL and quote_asset=USDT.

Listing facts are never promoted into a full Security or ContractRules record. Classification, current/continuous activity, tick/quantity/notional rules, contract-size semantics, maintenance tiers, LAST-stop capability and later rule changes remain missing. LISTING also produces no delisting/replay event and therefore cannot make a historical universe eligible by itself.

Eight official early-2020 Binance support pages were retained as reviewed acquisition candidates in docs/data/11j-legacy-listing-source-review.json. Their page text exposes useful launch facts, but raw CMS bytes/body hashes and original historical receipt evidence were not acquired in this milestone. The candidates therefore remain execution_eligible=false and cannot enter replay. Final remains LOCKED; no Alpha/risk/config value changed and no order was sent.

CI 35595263337 passes 499 tests plus Ruff, provenance, reference smoke and pinned Freqtrade lifecycle/parity checks.


## Exact-source funding settlement usability (Milestone 11K)

Funding settlement economics are now separated from position eligibility and funding-calendar coverage. The new source gate accepts only exact Regular funding-history rows with a non-null source-associated settlement Mark and exact source/revision identity. It preserves millisecond timestamps and never creates interval starts, rounds timestamps, fills missing Marks or infers an eight-hour schedule.

FundingEligibilityEvidence is a separate exact-boundary object carrying the owned position, side and eligible quantity. A FundingPayment can be created only when source economics and eligibility match the same symbol and exact settlement timestamp. Payment availability is the later of source availability and eligibility-evidence availability, and the deterministic event identity binds both source revision and eligibility evidence. This supports PRELIMINARY accounting for individually proven settlements without creating FundingCoverage or qualifying the 30-day funding reserve.

The pinned BTCUSDT January 2024 control has 93 Regular source rows and 93 source-associated settlement Marks, so 93 rows pass the conditional economics gate. Zero are unconditionally ledger-usable from public market history alone because historical position-boundary eligibility is a separate input. The broader source audit still retains 4,291 missing settlement Marks before November 2023. See docs/FUNDING_SETTLEMENT_USABILITY.md and docs/data/11k-funding-usability-control.json.

Fifteen new tests cover exact economics, eligibility mismatch, source/eligibility availability ordering, missing Marks, unsupported rate types, timestamp jitter, duplicate identities, schema strictness and deterministic evidence binding. Full CI 35598476129 passes 514 tests, Ruff, provenance, reference smoke and pinned Freqtrade lifecycle/parity checks. No Alpha/risk/config value changed, no performance result was produced and no external order was sent.


## Causal replay funding-boundary eligibility (Milestone 11L)

The exact-source funding path is now wired into AccountReplay. A PRELIMINARY funding event must match the selected source timestamp and provenance exactly and cannot arrive before the source row. Replay reconstructs the owned quantity at that settlement using only fills whose exchange event time is at or before the boundary and whose evidence is available by the replay seal. Fills occurring after settlement are excluded even when already known. Same-boundary entry/reduction mixtures without comparable exchange sequence fail closed.

A deterministic FundingEligibilityEvidence revision binds owner, settlement, replay seal and selected fills before M11K constructs FundingPayment economics. Flat boundaries emit no payment. Restart receipts remain idempotent. If a later-arriving fill has exchange event time at or before a boundary whose funding payment was already frozen, AccountCoordinator rejects it and replay latches reconciliation instead of silently revising historical funding.

This proves only causal strategy-position eligibility for individually evidenced settlements inside PRELIMINARY replay. It does not establish a complete funding calendar, FundingCoverage, original historical publication latency, external exchange-account eligibility, the 4,291 missing pre-November-2023 settlement Marks, or complete historical rule/security coverage. See docs/FUNDING_REPLAY_BOUNDARY.md.

Thirteen new tests cover exact owned quantity, pre-boundary reductions, post-boundary exclusions, late-fill invalidation, source timing/provenance, missing Marks, unsupported rate types, VERIFIED-promotion rejection, flat boundaries, restart idempotence and ambiguous same-time fills. Full CI 35599685386 passes 527 tests plus Ruff, provenance, reference smoke and pinned Freqtrade lifecycle/parity checks. No Alpha/risk/config value changed, no performance result was produced and no external order was sent.


## Pre-Final historical evaluation readiness gate (Milestone 11M)

A hard readiness boundary now sits in front of any historical performance run. The frozen gate covers Development + Validation from 2020-01-01 through the exclusive 2025-07-01 Final Test boundary and rejects attempts to widen the window, unlock Final Test, or pre-authorize performance/operations.

The committed matrix at docs/data/11m-pre-final-readiness.json contains eleven mandatory capabilities: historical universe, security master, contract rules, lifecycle, LAST 1h, LAST 1m, Mark 1m, funding settlement pricing, funding schedule, funding reserve, and liquidation rules. Each PARTIAL evidence file is pinned by exact Git blob identity plus semantic source/report anchors. Changed bytes, schema drift, a failed semantic anchor, duplicate/missing capability rows, path escape, or holdout-policy change fails closed.

M11M distinguishes source evidence from a completion attestation. An arbitrary source report cannot simply be relabeled COMPLETE. COMPLETE requires a dedicated PVB24_CAPABILITY_ATTESTATION_V1 spanning the entire frozen pre-Final window with explicit PRELIMINARY/VERIFIED quality and no gaps. MISSING and PARTIAL always block require_performance_ready().

The current repository matrix intentionally evaluates NOT READY: all eleven mandatory capabilities are PARTIAL. This accurately reflects the one-month BTCUSDT candle sample, reviewed-only announcement coverage, incomplete historical universe/rules, 4,291 missing settlement Marks, unqualified funding schedule/reserve, and missing historical liquidation tiers. The gate therefore prevents a six-year P&L from being generated from incomplete evidence rather than weakening any data rule.

The audit CLI is scripts/check_historical_evaluation_readiness.py; blocked readiness exits 2 and lists every blocking capability. Future historical performance entrypoints must call require_performance_ready() before producing strategy metrics. See docs/HISTORICAL_EVALUATION_READINESS.md.

Twelve new tests cover all-complete synthetic attestations, partial/missing blocking, prevention of self-declared completion, Final Test/window governance, evidence tampering, semantic-anchor mismatch, exact capability-set enforcement, full-window coverage and the real committed blocked matrix. Full CI 35601347834 passes 539 tests plus Ruff, provenance, reference smoke and pinned Freqtrade lifecycle/parity checks. No Alpha/risk/config value changed, no performance result was produced and no external order was sent.


## Pinned market-data capability attestation compiler (Milestone 11N)

A fail-closed compiler now provides the only promotion path for LAST_1H, LAST_1M and MARK_1M from archive evidence into COMPLETE historical-evaluation capabilities. It cannot use archive-directory presence, successful downloads or currently surviving symbols to define the historical universe. Instead, it requires a separately pinned COMPLETE HISTORICAL_UNIVERSE attestation spanning the frozen pre-Final window, and a SHA-256-pinned monthly obligation manifest bound to that exact universe attestation.

Each obligation expands into the exact Binance monthly archive requests required for its symbol/range. A month counts only when the selected acquisition report contains one unique ACQUIRED PRELIMINARY revision, monthly_bar_grid_complete=true, no gaps, and load_acquired() successfully re-hashes and re-decodes the retained ZIP and official CHECKSUM bytes. Missing archives, incomplete grids, corrupt retained objects, changed pins, duplicate revisions, non-month boundaries, holdout-crossing obligations or an incomplete universe attestation remain explicit blockers.

Only a gap-free capability can emit PVB24_CAPABILITY_ATTESTATION_V1. No repository COMPLETE attestation is emitted today because HISTORICAL_UNIVERSE remains PARTIAL; the current 11M readiness matrix therefore remains blocked. The compiler is available through scripts/audit_market_data_capability.py and documented in docs/MARKET_DATA_CAPABILITY_ATTESTATION.md.

Fourteen new tests cover complete synthetic coverage, missing/gapped months, retained-object corruption, universe-attestation integrity, obligation pinning, symbol/window/boundary rejection and governance flags. Full CI 35603211675 passes 553 tests plus Ruff, provenance verification, reference smoke and pinned Freqtrade lifecycle/parity checks. No Alpha/risk/config value changed, Final Test remains LOCKED, no historical performance result was generated and no external order was sent.


## Official announcement catalog discovery (Milestone 11O)

A bounded official Binance CMS catalog adapter now inventories source candidates from catalog 48 (New Cryptocurrency Listing) and catalog 161 (Delisting) without treating catalog membership or titles as historical trading eligibility. It validates catalog identity, exact integer release clocks, legacy 12-digit and modern 32-hex article codes, newest-first ordering, duplicate identities, bounded page size, and a stable observed catalog total within one acquisition slice.

Every retained raw catalog page is content-addressed by SHA-256 and revalidated before reuse. A caller must supply an explicitly reviewed starting page; the research engine does not crawl newer pages to discover where the pre-Final boundary begins. If any fetched row reaches or exceeds the requested pre-Final upper boundary, acquisition fails closed rather than filtering the row and continuing. This preserves the locked Final Test while still providing a scalable discovery path for older announcement candidates.

A successful catalog slice means only that the requested source slice reached its lower time boundary without source/pagination ambiguity. It never marks HISTORICAL_UNIVERSE, SECURITY_MASTER or LIFECYCLE complete. Candidate bodies still require explicit acquisition, body/facts hashing and semantic qualification through the existing announcement decoder, then reconciliation with causal archive activity.

The CLI is scripts/acquire_announcement_catalog.py and the source-policy notes are in docs/ANNOUNCEMENT_CATALOG_DISCOVERY.md. Twenty-one new tests cover source identity, legacy codes, ordering, pagination, page-total drift, duplicate/revision conflicts, retained-object tampering, Final-boundary rejection and governance flags. Full CI 35606070751 passes 574 tests plus Ruff, provenance, reference smoke and pinned Freqtrade lifecycle/parity checks. No Alpha/risk/config value changed, no performance result was generated and no external order was sent.


## Post-M11O manual-change review — initial CI repair

Reviewed scope: eecaab8 (M11O documentation), b7174c7 (announcement_inventory.py), 11ebe78 (inventory tests). Incoming HEAD 11ebe7861447d965afd6a0cf7e4b4b4314d5ac05 failed governance CI 35611762511 at Ruff formatting; Freqtrade smoke passed. Only those changes and their directly used catalog/announcement source contracts were inspected.

Root causes fixed: one unformatted condition; inventory incorrectly passed ISO/datetime catalog clocks to the archive integer-millisecond parser, causing all three new tests to fail once formatting was repaired; one exception-message assertion did not match the implementation. The inventory now accepts the catalog's actual aware ISO serialization (or aware datetime) without rounding, rejects naive times, and preserves the Final boundary. Four regression cases were added. Full suite: 581 passed; Ruff and frozen-source/config provenance verification passed.

Review remains open: a self-hashed report is not a pinned retained-source proof; catalog load_slice currently validates each raw page without rebuilding the selected article/page chain, and acquisition retains raw bytes before checking the upper boundary. These directly affect safe use of the new inventory and must be corrected before the manual work is approved or a production candidate inventory is published. No Alpha, thresholds, risk rules, readiness gate, funding, settlement, or frozen reference/config file was changed by the incoming manual commits or this repair. Candidates remain PRELIMINARY discovery hints, not available_at-qualified lifecycle facts. No data was acquired or performance run in this repair.


## Reviewed pinned announcement candidate inventory (Milestone 11P)

The manual commits eecaab8, b7174c7 and 11ebe78 were reviewed within their three-file diff and directly relevant source dependencies. Their candidate filtering, ordering and discovery-only semantics are retained. The initial formatting/timestamp/test-message repair was published at 7bed530b7907f8b3a2eeefe35e33924cae6300f5 and passed CI 35616597202 before the next work began.

Source fixes now bind public inventory construction to CatalogSlice(root, report, sha256) selections. load_slice replays retained raw pages, exact article selection, sequential URLs/page numbers, ordered acquisition receipts, declared total/page lengths, cross-page ordering and terminal evidence. Recomputed report hashes cannot fabricate articles or conceal missing pages. Invalid/mixed Final pages are checked before raw-object retention; unknown or inconsistent evidence stays INCOMPLETE. Naive source request clocks fail before network access. These fixes affect ingestion only; all historical strategy and risk rules are unchanged.

The new offline CLI scripts/build_announcement_inventory.py emits a content-addressed PRELIMINARY inventory with report/page/source pins and a filter implementation hash. Unmatched titles are counted and recall remains unverified. No candidate gets an available_at, lifecycle fact, complete-universe attestation, operational readiness or LIVE enablement. Source release time is not treated as historical body receipt timing. No production catalog inventory or performance result was created, and no dataset was redownloaded.

Validation: 602 tests passed; Ruff lint/format and original source/config verification passed. The new tests exercise actual serialized catalog reports, report/page tampering, forged titles/omissions, terminal-chain truncation/continuation, pagination drift, Final bytes not being retained, naive time rejection and the offline CLI. See docs/POST_M11O_REVIEW.md for root causes and exact remaining source prerequisite. M11P publication is accepted only once its own GitHub Actions run succeeds; inspect the branch's exact HEAD run rather than assuming the older CI result applies.
