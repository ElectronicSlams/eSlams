# Core inputs for a hosted Labs page

This is the **Core handoff contract** requested in issue #12. It defines source
inputs and acceptance criteria for a Platform implementation. It does not
establish that a hosted route, authenticated intake or external sample mirror
has shipped. Platform owns its route, storage, authentication and browser UI.

| Section | Core input | Platform behavior |
| --- | --- | --- |
| Quickstart | [LABS.md](LABS.md), published pin `eslams-core==0.6.1`, provider variable names | Show the tested keyless path and BYO-key boundary. Distinguish published installation from source changes. |
| Samples | [samples.json](../sample_runs/samples.json) | Allowlist sample IDs, kind, producer version/commit, SHA-256, validation profile and explicit Local/fixture status. Link only verified objects. |
| Upload and visualize | [artifact profiles](ARTIFACTS.md), [custody rules](PUBLIC_CUSTODY.md) | Distinguish private audit intake from public replay input, show authentication/disclosure rules and retain verification status. |

Acceptance criteria:

- The route shows a real page with Quickstart, Samples and Upload/visualize.
- Keyless examples work without a hosted account or provider credential.
- Sample IDs and SHA-256 values match the fetched bytes; unavailable mirrors
  are omitted rather than rendered as working downloads.
- Local fixtures and teaching failures remain clearly labeled. An upload or
  `official-proof` kind never becomes an Official/Grand Slam claim by itself.
- Public input uses validated public projections. Private audit archives have
  explicit intended recipients, storage/disclosure policy and access controls.
- Hosted visualizations retain upstream invalid/incomplete flags. Private
  session envelopes and recipient-only actions never enter public streams.
- Existing Battlefield replay/theater components may be linked or reused;
  Core does not require a second theater or a product retirement.

This document is implementable without an unclaimed HF namespace, warehouse
dump, production database mutation, or organization model credentials. Hosted
implementation and deployment remain separate from the Core consolidation PR.
