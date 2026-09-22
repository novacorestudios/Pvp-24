# Milestone 11 — Historical Universe / Security Master gap matrix

Checkpoint basis: `build/pvb24-v1` at
`2e5bf57f2d15d90ae98a4d3f28f4762e5bb10ff6`, PVB-24 CI #302 SUCCESS.

Frozen pre-Final window:
`[2020-01-01T00:00:00Z, 2025-07-01T00:00:00Z)`.

This matrix is a closure plan, not a readiness promotion. Final Test remains LOCKED,
historical performance remains blocked, PAPER remains NOT READY and LIVE remains
DISABLED.

| Dimension | Current retained evidence | Exact gap | Closure condition |
| --- | --- | --- | --- |
| Active contract history | M11V has 15 consistent preliminary listing candidates and 7 unresolved listing boundaries. | No market-wide causal active/inactive USDT-linear contract stream for the full pre-Final window. | Every potentially eligible contract epoch has source-pinned start/end state or remains explicit UNKNOWN; no current `exchangeInfo` backfill. |
| Listing start | M11V and later M11X work preserve official announcement facts plus archive boundary checks. | Seven M11V listing boundaries remain unresolved; retained-source recovery covers only a subset of historical launches. | Exact start is source-backed where qualified; unresolved boundaries remain UNKNOWN and block exact eligibility. |
| Delisting | M11V has 11 delisting events; audit logic preserves postponement and conflicting-revision semantics. | Market-wide delisting coverage is incomplete and some events cannot yet be paired to an unambiguous contract epoch. | Causal announcement/forced-settlement evidence is paired to the correct epoch without future knowledge. |
| Relisting / prior epochs | Reviewed facts and audit obligations can expose prior-epoch disclosures and duplicate-start conflicts. | No complete relisting epoch stream exists. | Every repeated symbol epoch is explicitly separated with causal start/end provenance or remains blocked. |
| Rename / symbol change | Security audit requires change-stream completion. | No complete rename/symbol-change history is retained. | Versioned rename transitions are source-pinned with effective and `available_at` times. |
| Classification | Current listing candidates are deliberately `UNKNOWN`; one reviewed hint exists for a non-crypto index case. | No complete causal CRYPTO / STABLECOIN / NON_CRYPTO classification history. | Classification is independently sourced as-of decision time; UNKNOWN remains ineligible. |
| Source revision identity | M11T durable bundle, M11V, M11X and audit reports are content-addressed. | Coverage is still partial even though identities are strong. | Every consumed transition names exact source revision/hash; replacements are explicit, never silent. |
| Point-in-time availability | Security Master audit V5 preserves per-source `available_at` and evidence timelines. | Only currently retained sources are covered. | Every selected transition is unavailable before the exact source that establishes it. |
| Publication-time certainty | Existing reports keep `historical_publication_times_verified=false` where not independently proven. | Current CMS timestamps cannot automatically prove what was historically visible. | Historical visibility is independently qualified or stays PRELIMINARY. |
| Current metadata leakage | `historical_metadata.py` refuses to treat a current snapshot as earlier truth. | No complete versioned historical `exchangeInfo` stream exists. | Historical snapshots/change events are source-pinned; today's metadata is never projected backward. |
| Durable parser coverage | Audited M11T baseline recorded 28 qualified / 120 semantic-unqualified. Current deterministic replay over the same 148 retained source bytes produces 84 qualified / 64 semantic-unqualified, with 56 status promotions and 4 reason-only changes. | The improved parser result is diagnostic only and is not a separately qualified downstream artifact. | Emit an explicit successor artifact from the exact retained bytes, preserve the old baseline unchanged, bind lineage and same-SHA CI, then independently reconcile newly qualified lifecycle facts. |

## First executable root cause

The durable evidence layer already preserves all 148 announcement source responses by
content hash. The current parser can extract additional lifecycle facts from those exact
bytes, but the project intentionally prevents those diagnostics from silently replacing
the audited baseline. Consequently, usable retained evidence is stranded between parser
replay and downstream Security Master compilation.

The first closure step is therefore **not** to mutate M11T/M11V. It is to create a
separate, versioned retained-source requalification artifact with these invariants:

1. exact M11T durable bundle identity is required;
2. the original qualification report remains immutable;
3. every source byte is reverified before parsing;
4. previously-qualified semantics must remain byte-for-byte semantically identical;
5. only previously-unqualified rows may be promoted by the current parser;
6. the successor stays PRELIMINARY and cannot claim universe/security completeness;
7. Final Test remains LOCKED, PAPER remains NOT READY and LIVE remains disabled;
8. same-SHA CI and evidence payload sealing remain mandatory.

After this artifact is green and qualified, the next step is to reconcile the newly
qualified lifecycle facts against causal archive activity and then feed only
non-conflicting source-backed transitions into the Security Master obligation audit.
Classification, rename/relisting and full market-window coverage remain independent
blockers and are not solved by parser requalification alone.
