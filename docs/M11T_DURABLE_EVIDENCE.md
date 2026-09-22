# M11T durable source evidence

Finding F6 requires the source evidence used by M11V/M11X to remain independently
restorable after GitHub Actions retention expires.

The original successful source run is pinned in
`docs/data/11t-source-artifacts.json`. That pin records the exact run SHA, artifact
IDs, artifact ZIP SHA-256 values, sizes, member counts, uncompressed sizes and
report hashes. Expiry metadata is retained for audit history but is not the durable
locator.

`.github/workflows/m11t-durable-evidence.yml` downloads those exact archives while
they are still available, verifies every source pin, builds a deterministic
content-addressed bundle, verifies an independent restore, and commits only the
bundle plus `docs/data/11t-durable-evidence.json` to `build/pvb24-v1`.

The durable locator contains the repository-relative bundle path and both the
outer bundle SHA-256 and embedded manifest SHA-256. The embedded manifest records
every file path, byte size and SHA-256 from the five source artifacts. Restore
rejects hash drift, duplicate members, path traversal, symlinks, unexpected bundle
members and attempts to overwrite different evidence.

After preservation, consumers must use
`scripts/durable_m11t_evidence.py restore` with the committed locator. They must
not substitute a newly downloaded current revision for the pinned 2026-09-21 source
revision if the old Actions artifacts disappear.

This bundle is evidence only. It does not enable LIVE trading, does not unlock the
Final Test and does not change strategy, risk, sizing, leverage, entry or exit
semantics.
