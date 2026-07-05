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
