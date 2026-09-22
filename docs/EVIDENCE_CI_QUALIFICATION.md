# Evidence CI qualification

Evidence workflow success is not sufficient to qualify an evidence artifact.

A qualified artifact must now satisfy all of the following on the exact producer
commit:

1. the producer ref is `build/pvb24-v1`;
2. a `PVB-24 CI` run exists for the exact 40-character producer SHA;
3. the CI run is completed successfully;
4. both `governance` and `freqtrade-smoke` belong to that same CI run and both
   completed successfully;
5. the evidence workflow records the producer SHA and CI run ID in
   `evidence-qualification.json`;
6. every payload file is hashed by SHA-256 and the file inventory is itself hashed;
7. the qualification manifest is verified immediately before upload or durable
   preservation.

The gate deliberately rejects the historical failure mode where an evidence
workflow was green while CI on the same SHA was red. A prior green run from a
different SHA, or successful jobs taken from different CI runs, cannot satisfy the
gate.

Manual dispatch is restricted to `build/pvb24-v1` for production evidence jobs.
Workflow path filters include the qualification helper dependencies so a policy
change cannot leave evidence workflows silently using an older qualification
implementation.

This mechanism does not unlock Final Test, does not enable LIVE and does not alter
Strategy/Alpha, thresholds, sizing, leverage, risk, entry or exit logic.
