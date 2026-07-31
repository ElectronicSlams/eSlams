# Security

Do not report security issues in public GitHub issues.

Report vulnerabilities to security@eslams.com. Include the affected package,
version or commit, reproduction steps, and whether any hidden eval material,
provider credentials, artifacts, or replay data may be exposed.

You can also use GitHub private vulnerability reporting:
https://github.com/ElectronicSlams/eSlams/security/advisories/new

Artifact signatures are provenance checks, not magic trust. A local signature
only proves that the configured keyholder vouched for that artifact; local runs
may be self-signed. Treat signatures as externally trusted only when the public
verification key and keyholder are trusted for the run profile being claimed.

Security-sensitive areas include:

- hidden state leakage
- hidden official eval material
- trace redaction bugs
- artifact-signing bugs
- sandbox escapes
- provider credential handling
- leaderboard verification bypasses

## Provider and Artifact Boundaries

Provider credentials are read only from the documented environment variables.
Do not place credentials in CLI arguments, model registry rows, fixtures,
artifacts, provider receipts, error messages, or public replay packages. Error
bodies are bounded and redacted, but callers should still avoid sending secrets
inside prompts or provider-controlled metadata.

Public provider-attempt events contain routing identity, timestamps, normalized
usage/cost fields, parse/apply status, and request IDs only. They must never
contain prompts, private observations, authorization headers, raw provider
responses, or hidden reasoning. Private audit objects may retain normalized
usage or a raw-usage hash only when deployment policy explicitly permits it.
Provider endpoint identifiers must be absolute HTTPS or local mock URIs without
userinfo, fragments, or credential-bearing query parameters. Receipt validation
recursively rejects sensitive field names and unredacted bearer or URL secrets,
including receipts produced outside Core.

Explicit run IDs are portable path-safe identifiers and cannot select paths
outside the configured output directory. Artifact output symlinks are never
followed for overwrite. The `latest.eslams` and `latest.eslams.d` aliases may
replace existing symlinks only; real files and directories are preserved and
cause publication to fail closed.

Official-case validation is fail-closed. A signature does not repair a fallback,
provider failure, missing attempt, incomplete usage/cost record, route mismatch,
or broken trace/replay/receipt join. Downstream systems may make Core validity
stricter; they must never turn an upstream invalid or incomplete run into valid.

Use a reviewed `eslams.price-card-reference.v1` object for complete cost claims.
An arbitrary rate-card string is diagnostic metadata and cannot prove cost
completeness. Treat price-card hashes and sources as signed-plan inputs in
official infrastructure.

## Supported Versions

Security fixes are made on the latest release line. Core 0.6 can read selected
0.5 artifact/receipt history, but historical signatures and contracts do not
gain current official trust merely because they remain readable.
