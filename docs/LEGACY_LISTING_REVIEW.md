# Legacy Binance Futures listing evidence path — M11J

The six-year historical reconstruction cannot rely only on modern 32-hex Binance announcement
identifiers. Official Binance support pages from early 2020 use 12-digit numeric article IDs.
M11J extends the reviewed announcement adapter to accept **only** either a 12-digit legacy ID
or the existing 32-hex ID.

The new `LISTING` fact parser is deliberately narrow. For a retained legacy CMS body it requires
one explicit Binance Futures USDT perpetual symbol, one explicit UTC launch timestamp and one
announced maximum leverage. It emits only:

- symbol;
- launch_at;
- max_leverage;
- contract_type=PERPETUAL;
- quote_asset=USDT.

It does **not** infer crypto/stablecoin classification, current activity, tick size, quantity
step, minimum notional, contract-size semantics, maintenance tiers, stop capability or later
rule changes. A listing fact therefore cannot become a complete `Security` or `ContractRules`
record and cannot make historical-universe coverage complete.

`docs/data/11j-legacy-listing-source-review.json` records eight official pre-Final support pages
reviewed as acquisition candidates. They establish that useful legacy launch facts are publicly
visible, but raw CMS bytes were not retained in this milestone. Consequently those candidate
rows are **not executable evidence** and are not injected into replay. They require the normal
body SHA-256 + independently reviewed facts hash before acquisition can succeed.

The existing announcement availability rule remains PRELIMINARY: the currently retained CMS
revision becomes usable only at publication or a known later update plus two seconds; this is
not proof of the original historical receipt time. Final Test access remains locked.

This work removes a source-format blocker while preserving the larger blockers: complete
security classification/history, full historical contract rules, maintenance/leverage tiers,
funding settlement Mark gaps, funding position eligibility, and sequence-consistent L2.
