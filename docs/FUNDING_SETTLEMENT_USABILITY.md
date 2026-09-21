# M11K: exact-source funding settlement usability

This milestone separates three independent questions that were previously easy to conflate:

1. **Settlement economics:** does the selected official funding-history row contain an explicit
   Regular final rate and a source-associated settlement Mark at the exact source timestamp?
2. **Position eligibility:** is there independent evidence of the owned position side and
   quantity that was eligible at that exact settlement boundary?
3. **Funding schedule/coverage:** is the complete settlement calendar known well enough to prove
   that no settlement is missing and to construct continuous `FundingSettlement` intervals?

Only (1) is available from the reviewed funding-history source. M11K therefore does **not**
invent interval starts, round millisecond timestamps, infer an eight-hour calendar, fill missing
Marks, or turn the last observed row into a coverage watermark.

`FundingEligibilityEvidence` is a separate, exact-boundary object. A source row can become a
`FundingPayment` only when both symbol and settlement timestamp match that evidence exactly and
the row has `rate_type=Regular` plus a non-null settlement Mark. Payment availability is the
later of source availability and eligibility-evidence availability. The event identity binds the
source revision, exact economics, and eligibility evidence.

This can support PRELIMINARY accounting for individually proven settlements. It does not produce
`FundingCoverage` and cannot by itself qualify the 30-day P95 funding reserve. Historical
publication timing remains modelled, not verified.

## Actual January 2024 control

The previously pinned BTCUSDT January 2024 source comparison contains 93 official funding-history
rows. All 93 are explicit Regular rows and all 93 carry source-associated settlement Marks, so
their **economics** satisfy the conditional M11K row gate. However, there is no independently
qualified historical position-boundary evidence in the repository, so zero rows are
unconditionally ledger-usable for a real historical strategy position. The month also does not
establish a complete historical funding calendar.

The broader M11G audit still has 4,291 missing source Marks before November 2023. M11H already
showed why Mark OHLC cannot substitute for those missing prices.

Final Test remains LOCKED. No strategy Alpha/risk/threshold/config values are changed; no
performance result or PAPER/LIVE readiness is inferred.
