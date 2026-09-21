# Source evidence recovery — 11G

The user-owned file `PVB24-source-evidence-11G.zip` preserves 508 original evidence files for these ignored data roots:

- data/acquisition-11a-final
- data/funding-11e
- data/announcements-11f
- data/funding-11g

Archive size: 4607372 bytes. SHA-256: `85206d50a6148bbbafb285c69eece7fa1a1c8ebd592cb485bdb5448286f7baeb`.

The ZIP includes SOURCE_EVIDENCE.json with per-file SHA-256, sizes, exact relative paths, the final Funding summary and its selected data identity. The manifest content hash is `2b5bfb58457426104602f3e985a638b326abb4b98dba0fda068da6bd8f4ba089`. ZIP CRC and every member hash were verified before saving. Source code/configuration remain exclusively in Git; this bundle is raw acquisition evidence, not a second repository or executable release.

On a fresh workspace, retrieve this exact named bundle, verify its archive SHA-256, inspect the embedded manifest, then extract its data directories into the repository root without overwriting different existing files. Reconsumption must still use the committed manifest/report pins and relevant source-reader integrity checks. If the bundle hash differs, stop; do not regenerate an apparently equivalent bundle from revised remote sources. A newly acquired source revision requires explicit new provenance/selection.

The complete original CMS responses are retained privately in the bundle. Public Git contains only their reviewed facts and source hashes, not copied announcement articles. No account credentials, live order capability or Final Test market data are included.
