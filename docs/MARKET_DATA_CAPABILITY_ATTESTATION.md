# Market-data capability attestation — Milestone 11N

Milestone 11M blocks historical performance until every mandatory capability is complete.
Milestone 11N adds the fail-closed compiler needed to close three of those capabilities
without allowing market-data availability to define the historical universe.

The compiler covers:

- `LAST_1H`;
- `LAST_1M`;
- `MARK_1M`.

It requires a separately pinned, COMPLETE `HISTORICAL_UNIVERSE` capability attestation
covering the entire frozen pre-Final window. A market-data obligation manifest is SHA-256
pinned to that exact universe attestation and lists only explicit USDT-linear symbol/month
ranges. This prevents today's archive directory, successful downloads, or surviving symbols
from being used to invent historical eligibility.

For each obligation the compiler expands the exact required monthly Binance archive requests.
A month counts only when the selected acquisition report contains one unique ACQUIRED
PRELIMINARY revision, its monthly grid is complete with no gaps, and
`load_acquired()` successfully re-hashes and re-decodes the retained ZIP and official
CHECKSUM object. A manifest claiming success while its retained bytes are missing or changed
does not pass.

Only a gap-free capability emits `PVB24_CAPABILITY_ATTESTATION_V1`. Missing files,
incomplete grids, invalid retained objects, duplicate revisions, changed pins, non-month
boundaries, Final-period obligations, or an incomplete universe attestation remain blocked.

This milestone intentionally does not create a repository attestation today: the historical
universe is still PARTIAL, so there is no legitimate obligation set to certify. It provides
the promotion path that will be used after the universe/security/lifecycle work is qualified.
It does not open Final Test, run strategy performance, or change Alpha/risk/configuration.
