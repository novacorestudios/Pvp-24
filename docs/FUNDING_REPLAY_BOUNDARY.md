# M11L: causal replay funding-boundary eligibility

Milestone 11L wires the M11K exact-source funding economics gate into the shared
AccountReplay without turning observed funding rows into a historical funding
calendar.

## Boundary rule

An exact-source funding replay event must remain PRELIMINARY. Its event time must
equal the source funding timestamp exactly, its replay availability cannot precede
the selected source row, and its event source must match the retained source
identity.

At delivery, the replay reconstructs the owned strategy quantity at the exact
settlement boundary from immutable fill evidence:

- only fills for the owned position with exchange event time at or before the
  settlement are eligible;
- only fill evidence received by the replay seal time is usable;
- fills occurring after settlement are excluded even if already known when the
  funding row is processed;
- owner registration must already exist at the boundary;
- an unsequenced same-time mixture of entry and reduction fills is ambiguous and
  fails closed instead of guessing an order;
- conflicting exchange sequences or a reduction exceeding known owned quantity
  also fail closed.

A deterministic eligibility revision binds the owner, exact boundary, replay seal
time and all selected fill evidence. That evidence is then combined with the M11K
source rate/Mark row to create a FundingPayment. Flat positions produce no payment.

## Late evidence

After a funding payment has frozen boundary eligibility, a newly arriving fill whose
exchange event time is at or before that settlement would revise the frozen
quantity. AccountCoordinator now rejects such a fill with
ReconciliationRequired. AccountReplay consequently latches its existing recovery
pause instead of silently rewriting historical funding cashflow.

This is intentionally conservative. A later fill occurring after the settlement
does not revise the boundary and is allowed.

## What this proves

The shared replay can now account for an individually evidenced funding settlement
using:

1. exact source rate and source-associated settlement Mark;
2. the strategy's causal owned quantity at that exact boundary; and
3. deterministic availability/provenance binding.

The path is restart-idempotent and uses the existing atomic coordinator/ledger
transaction semantics.

## What this does not prove

M11L does not establish:

- a complete historical funding schedule or FundingCoverage watermark;
- original historical publication latency for the public funding endpoint;
- the 4,291 settlement Marks still missing before November 2023;
- complete historical security/universe/rule snapshots;
- exchange-account eligibility as VERIFIED external evidence;
- six-year historical performance;
- PAPER or LIVE readiness.

The replay-derived position boundary is therefore PRELIMINARY evidence inside the
offline reference run, not a claim about unavailable historical exchange-account
records.

CI run 35599685386 passes 527 tests plus Ruff, provenance verification, reference
smoke and the pinned Freqtrade lifecycle/parity checks. No Alpha, thresholds, risk
configuration or Final Test policy changed, and no external order was sent.
