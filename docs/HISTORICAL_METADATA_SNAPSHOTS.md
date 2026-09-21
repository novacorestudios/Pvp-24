# Historical contract/security snapshot qualification

Milestone 11I adds an **offline, fail-closed** ingestion path for caller-pinned Binance USD-M
`exchangeInfo` captures. It does not download current metadata and does not use a present-day
response as evidence for an earlier date.

A selection must pin every retained JSON object by SHA-256 and provide its causal
`observed_at` and `available_at` timestamps. An earlier `effective_from` is accepted only when
`historical_effective_time_verified=true`; otherwise the observation itself is the earliest
permitted effective time. Final Test timestamps beginning 2025-07-01 remain rejected.

The source parser extracts only fields carried by the retained `exchangeInfo` response:
listing/onboard time, trading status, contract type, quote asset, PRICE_FILTER tick size,
LOT_SIZE quantity bounds/step, MIN_NOTIONAL/NOTIONAL minimum notional, and whether IOC appears
in the advertised time-in-force set. Duplicate symbols or duplicate filter types are ambiguous
and fail closed.

`exchangeInfo` alone is deliberately insufficient to promote historical metadata to VERIFIED.
The qualification report keeps the following evidence gaps explicit instead of inventing
values:

- security classification;
- contract-size semantics;
- historical maintenance/leverage tiers;
- LAST-price stop capability;
- completeness of the historical metadata change stream.

Therefore the generated security record keeps `classification=UNKNOWN` and
`historical_verified=false`, and the report keeps `security_history_complete=false`,
`contract_rule_history_complete=false`, `liquidation_tiers_complete=false`,
`quality=PRELIMINARY`, `operational_ready=false`, and `final_test_access=LOCKED`.

## Selection shape

```json
{
  "schema": "PVB24_EXCHANGE_INFO_SELECTION_V1",
  "final_test_access": "LOCKED",
  "change_stream_complete": false,
  "snapshots": [
    {
      "symbol": "BTCUSDT",
      "source_url": "https://fapi.binance.com/fapi/v1/exchangeInfo",
      "object": "objects/<sha256>.json",
      "revision_id": "<sha256>",
      "observed_at": "2024-01-02T00:00:00+00:00",
      "available_at": "2024-01-02T00:00:01+00:00",
      "historical_availability_verified": true,
      "historical_effective_time_verified": false
    }
  ]
}
```

The raw object must be stored under the selection root at the exact content-addressed path. The
selection itself must also be supplied with an explicit SHA-256 pin. Reconsumption re-hashes
both the selection and every raw object.

## Offline audit

```bash
.venv/bin/python scripts/audit_historical_metadata.py \
  --root data/historical-metadata \
  --selection data/historical-metadata/selection.json \
  --selection-sha256 <sha256> \
  --output data/historical-metadata-qualified
```

The command performs no network I/O. It writes a content-addressed report containing source
and timing provenance, extracted fields, explicit gaps, implementation hashes, repository SHA,
and the frozen project provenance. It is qualification infrastructure, not proof that a full
historical rules/security dataset currently exists.
