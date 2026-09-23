# Lab Quickstart

Pin: `eslams-core==0.6.1` · Contact: [hello@eslams.com](mailto:hello@eslams.com) · [eslams.com](https://eslams.com)

This page is the stranger-ready path for a **local** lab run.

**Local Artifact ≠ Official / Grand Slam.**

---

## What this is / is NOT

| This **is** | This is **NOT** |
| --- | --- |
| A local path to install Core, bring your own provider keys, run game evals, validate `.eslams` artifacts, and optionally visualize uploads | An **Official** or **Grand Slam** scoring path |
| Lab / researcher / hobbyist BYO evaluation | A live **leaderboard** product (the Platform leaderboard is retired / retiring) |
| Public OSS fixtures in this repo for inspection | Access to eSlams org provider keys or hidden official seeds |
| Local Artifact production under MIT Core | A claim that your Local Artifact equals platform-sealed Official proof |

Official scoring uses server-controlled infrastructure, secret seeds, and private scenario sets on eslams.com. A lab run is yours to inspect and share as a **Local** proof package. It is not an official seal, and labs are not a public leaderboard.

---

## Install (pinned)

The PyPI package name is `eslams-core` (`pyproject.toml` `version = "0.6.1"`). Python 3.9–3.12. Prefer a venv:

```bash
python -m venv .venv
. .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install eslams-core==0.6.1
```

Do not unpin to “latest” for lab docs or CI that should match this release.

The smoke suite lives in the git checkout, not in the wheel. Clone this repo when you want `suites/lab-smoke/`:

```bash
git clone https://github.com/ElectronicSlams/eSlams.git
cd eSlams
python -m venv .venv
. .venv/bin/activate
pip install eslams-core==0.6.1
```

Contributors can use `pip install -e ".[dev]"` from this checkout instead. That editable install is still Core `0.6.1` on this release line.

---

## BYO provider credentials

Core reads credentials **only** from environment variables. Labs bring **their own** keys. Never use or request eSlams org provider keys.

| Provider | CLI agent form | Credential env var |
| --- | --- | --- |
| OpenAI | `openai:<model>` | `OPENAI_API_KEY` |
| Anthropic | `anthropic:<model>` | `ANTHROPIC_API_KEY` |
| Google Gemini | `gemini:<model>` | `GEMINI_API_KEY` |
| OpenRouter | `openrouter:<vendor/model>` | `OPENROUTER_API_KEY` |
| Amazon Bedrock | `bedrock:<model-id>` | `AWS_BEARER_TOKEN_BEDROCK` |

```bash
export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
export GEMINI_API_KEY=...
export OPENROUTER_API_KEY=...
export AWS_BEARER_TOKEN_BEDROCK=...
```

Set only the credential for the provider you will call. Wire adapters, preflight, and model identity rules are in [docs/PROVIDERS.md](PROVIDERS.md).

### Secrets posture

- Labs bring their own keys. Never use or request eSlams org provider keys.
- Do not put lab provider keys in Platform workers, GitHub Actions, or shared demo Spaces.
- Do not put credentials in CLI args, fixtures, artifacts, receipts, prompts, or public replays.
- Follow [SECURITY.md](../SECURITY.md): env-only credentials. Report vulnerabilities to `security@eslams.com`, not in public issues.

---

## Under 15 minutes

### 1) Keyless random / first-legal (~2 min)

No API keys:

```bash
eslams init
eslams run \
  --arena connect-four \
  --agent random \
  --opponent first-legal \
  --execution-profile smoke \
  --verification-level "Local Artifact"
eslams validate runs/latest.eslams --profile runner-bundle
eslams replay runs/latest.eslams
```

You get `runs/<run_id>.eslams`, an expanded `.eslams.d` tree, and `runs/latest.eslams` pointers. The verification level on that package is **Local Artifact**.

The same keyless idea, across four arenas, is the checked-in suite. From the repo root:

```bash
python suites/lab-smoke/run_keyless.py
```

That runs 10 builtin cases (tic-tac-toe, connect-four, othello, chess), validates each archive, and refuses `provider:model` agents. Details: [suites/lab-smoke/README.md](../suites/lab-smoke/README.md).

### 2) One BYO keyed smoke (~5–10 min)

Pick one provider you already have a key for. Example: OpenAI. This calls your account and costs a little.

```bash
export OPENAI_API_KEY=...   # your key only

# Offline registry check. This is not an availability claim.
eslams providers preflight \
  --provider openai --model gpt-5-mini --arena tic-tac-toe

# Live: account discovery plus one bounded inference.
eslams providers preflight \
  --provider openai --model gpt-5-mini --arena tic-tac-toe --live

eslams run \
  --arena tic-tac-toe \
  --agent openai:gpt-5-mini \
  --opponent first-legal \
  --execution-profile smoke \
  --verification-level "Local Artifact" \
  --on-agent-error invalid-match \
  --on-illegal-action invalid-match

eslams validate runs/latest.eslams --profile runner-bundle
eslams replay runs/latest.eslams
```

Other one-liners after exporting the matching key:

```bash
eslams run --arena tic-tac-toe --agent anthropic:claude-sonnet-4-20250514 --opponent first-legal --execution-profile smoke --verification-level "Local Artifact"
eslams run --arena tic-tac-toe --agent gemini:gemini-2.5-flash --opponent first-legal --execution-profile smoke --verification-level "Local Artifact"
eslams run --arena tic-tac-toe --agent openrouter:openai/gpt-5-mini --opponent first-legal --execution-profile smoke --verification-level "Local Artifact"
# Bedrock: the CLI splits provider:model on the first colon. :0 in the model id is literal.
eslams run --arena tic-tac-toe --agent bedrock:amazon.nova-micro-v1:0 --bedrock-region us-east-1 --opponent first-legal --execution-profile smoke --verification-level "Local Artifact"
```

Keep fail-closed policies explicit for comparison runs (`--on-agent-error invalid-match`, `--on-illegal-action invalid-match`). Those are already the CLI defaults. Opt-in `--on-agent-error fallback` or `--on-illegal-action fallback` marks the run invalid for scoring. That is fine for a demo and wrong for a battle-sample claim.

`--execution-profile smoke` is a local lab profile. It is not `--execution-profile official_eval`, and it does not produce Official or Grand Slam verification.

### 3) Inspect curated samples in this repo

In-repo samples are fixtures and publication-bundle examples, not a live leaderboard feed:

- [sample_runs/README.md](../sample_runs/README.md)
- [sample_runs/model_eval_sample/README.md](../sample_runs/model_eval_sample/README.md)
- [sample_runs/model_battle_sample/README.md](../sample_runs/model_battle_sample/README.md)

Public Battlefield demos: [eslams.com/battlefield](https://eslams.com/battlefield).

Hugging Face sample packs are not part of this quickstart. Do not treat a future dataset download as Official scoring or as a public leaderboard.

---

## Upload for visualize (not an official seal)

1. Validate locally (`eslams validate … --profile runner-bundle`).
2. Upload via eslams.com Artifact Intake / Trinity (developer sign-in: GitHub, Google, or email).
3. Inspect replay, score, and proof UI after ingest.

That visualizes your **Local Artifact**. It does not convert the package into Official or Grand Slam sealed scoring. For paid official evaluation, contact [hello@eslams.com](mailto:hello@eslams.com).

---

## Security and leave-behind

- Security posture: [SECURITY.md](../SECURITY.md) — env-only keys, no secrets in artifacts, report to `security@eslams.com`.
- Providers: [docs/PROVIDERS.md](PROVIDERS.md)
- Arenas: [docs/ARENAS.md](ARENAS.md)
- Lab smoke suite: [suites/lab-smoke/README.md](../suites/lab-smoke/README.md)
- Product questions: [hello@eslams.com](mailto:hello@eslams.com)
- Site: [https://eslams.com](https://eslams.com)
- Core repo: [https://github.com/ElectronicSlams/eSlams](https://github.com/ElectronicSlams/eSlams)

---

## Status

| Item | State |
| --- | --- |
| Package pin | `eslams-core==0.6.1` |
| Lab smoke | `suites/lab-smoke/` — keyless Local Artifact only |
| Live leaderboard as a lab product | Retired / retiring — labs are not a public leaderboard |
| Official / Grand Slam | Not produced by this quickstart |
