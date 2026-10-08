# Sample classifications and mirrors

The machine inventory is [sample_runs/samples.json](../sample_runs/samples.json).
It records sample ID, archive SHA-256, content artifact ID, GitHub path,
producer Core version and immutable commit, kind, expected validation profile,
Official trust, and verified mirror status. Both current examples are
`LOCAL_FIXTURE`, with `dual_home: false` and `hf_url: null`.

| Classification | Requirement |
| --- | --- |
| `LOCAL_FIXTURE` | Complete keyless example; runner/publication validation passes; no independent Official trust or provider-performance claim. |
| `TEACHING_FAILURE` | Explicit expected error/profile and safe public projection. Never silently counted as a successful or eligible run. |
| `HISTORICAL` | Producer version/commit recorded. Inspect with the producer's isolated environment; do not promote old signatures or eligibility flags to current trust. |
| `PRIVATE_REVIEW` | No public-export/disclosure attestation. Keep raw bytes and private state with intended auditors. |

The previous sample docs misidentified a truncated built-in chess run as a
provider-model battle. The legacy HMAC `official_signed` sample also failed
current Official validation. Those newcomer examples are replaced with complete
keyless fixtures. Existing historical bytes remain available in Git history;
no original result is re-signed or retroactively relabeled as a successful
current Official result. Legacy-HMAC rejection remains tested.

The `official-proof` bundle kind in the eval example describes an ingestion
shape. Its source is unsigned and its proof-row eligibility is false. It is
not an Official evaluation, hidden suite or model comparison.

To regenerate review candidates:

```bash
python scripts/generate_sample_fixtures.py --out /path/to/new/scratch-directory
```

Review the archives and bundles before installing them in the sample tree.
Fixed fixture timestamps are test metadata; measured timing sidecars remain
diagnostic. The producer commit is part of the artifact and must be preserved
in the inventory. Current artifacts contain no developer filesystem paths;
public proof indices use content IDs instead of source paths.

For future mirrors, add an exact project-controlled URL only after fetching
and checksum-verifying the bytes. `dual_home: true` requires matching GitHub
and mirror objects, not a planned repository name. Unclaimed namespaces,
placeholder Collection slugs, proposed archive tiers and unsigned scrub claims
do not meet this criterion. No HF publication is part of this consolidation.

Published 0.4.0/0.5.0 sdists contain historical planning notes; those published
files are immutable. The 0.6.1 sdist no longer includes those notes. This source
adds an explicit sdist include list and verifies built distributions from an
isolated checkout. Historical files are not republished, yanked or deleted by
this repair. Use a clean reviewed commit/tag for a future release.

See [custody and claims](PUBLIC_CUSTODY.md), [artifact migration](ARTIFACTS.md)
and the individual sample READMEs for expected command results.
