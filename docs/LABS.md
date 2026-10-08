# Local lab quickstart

Install the published engine in a fresh Python virtual environment. The package
pin below is **published 0.6.1**, not the unreleased changes in PR #218. Published
0.6.1 requires Python 3.9+; this proposed source branch requires Python 3.10+.
Use Python 3.12 for this walkthrough.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install eslams-core==0.6.1
eslams init
eslams run --arena connect-four --agent random --opponent first-legal
eslams validate runs/latest.eslams --profile runner-bundle
eslams replay runs/latest.eslams
```

On Windows, activate with `.venv\Scripts\Activate.ps1` in PowerShell. Commands
write a Local Artifact archive, an expanded inspection directory, latest
pointers and a replay HTML file. No provider key or hosted account is needed.
Open the reported HTML file in your browser. **Local Artifact ≠ Official or
Grand Slam.** Validation checks the artifact's contents; it does not confer
independent trust in a local keyholder or produce a public rank.

For the proposed source changes, clone the repository, use a separate virtual
environment and run `python -m pip install -e ".[dev]"` instead of the PyPI
installation. The native/distribution gates test this source independently;
the old wheel does not gain these repairs.

## Bring your own provider key

| Provider | Agent form | Credential variable |
| --- | --- | --- |
| OpenAI | `openai:<model>` | `OPENAI_API_KEY` |
| Anthropic | `anthropic:<model>` | `ANTHROPIC_API_KEY` |
| Gemini | `gemini:<model>` | `GEMINI_API_KEY` |
| OpenRouter | `openrouter:<vendor/model>` | `OPENROUTER_API_KEY` |
| Bedrock | `bedrock:<model-id>` | `AWS_BEARER_TOKEN_BEDROCK` |

Set only your chosen provider's variable in your own environment. Keep keys out
of commands, commits, artifacts and public pages. Neither this guide nor Core
CI supplies organization keys. Use the current [provider guide](PROVIDERS.md)
for supported adapters and account-visible model discovery. A registry listing
does not prove that your account can call a model or that it supports a game.

After choosing a model and exporting your credential, the proposed CLI can
check metadata offline and explicitly opt into a live preflight:

```bash
eslams providers preflight --provider openai --model YOUR_MODEL --arena tic-tac-toe
# --live queries model discovery and makes a small inference request using your key.
eslams providers preflight --provider openai --model YOUR_MODEL --arena tic-tac-toe --live
eslams run --arena tic-tac-toe --agent openai:YOUR_MODEL --opponent first-legal --execution-profile smoke
```

Live preflight and model runs incur your provider's usage charges. Keyless
`random`/`first-legal` runs remain available. Fail-closed defaults keep failed,
illegal, fallback or early-truncated actions unscoreable. Offline checks and a
passing smoke do not certify Official eligibility.

## Samples and public sharing

The supported sample download is this repository's [sample tree](../sample_runs/README.md).
[Classification and checksums](SAMPLE_CLASSIFICATION.md) distinguish current
Local fixtures from historical/invalid material. No Hugging Face dataset,
Collection or Space is promised by this guide. An external host must be
verified, project-controlled and checksum-matched before it becomes a download
source. A similarly named organization is not proof of ownership.

Runner archives contain private auditor state and agent I/O. Keep them in
private custody. For public viewing, use a **new** output directory:

```bash
eslams artifact public-export runs/latest.eslams --out public_replay_package
eslams validate public_replay_package --profile public-replay-package
eslams replay public_replay_package
```

Public exports omit auditor/private traces. A hosted upload needs its own
intake, access controls and disclosure policy; this guide does not promise a
particular hosted route or automatic publication. See [public custody](PUBLIC_CUSTODY.md)
and the [Platform handoff](LABS_PAGE_CONTRACT.md).

For keyless checks across all arenas, use `eslams arena smoke --all --json`.
For source tests and distribution checks, follow [CONTRIBUTING.md](../CONTRIBUTING.md).
Questions: hello@eslams.com. Vulnerabilities: [SECURITY.md](../SECURITY.md).
