# Lab Quickstart

> Wave A · pin `eslams-core==0.6.1` · Contact: [hello@eslams.com](mailto:hello@eslams.com) · [eslams.com](https://eslams.com)

---

## What this is / is NOT

| This **is** | This is **NOT** |
| --- | --- |
| A local path to install Core, bring your own provider keys, run game evals, validate `.eslams` artifacts, and optionally visualize uploads | An **Official** or **Grand Slam** scoring path |
| Lab / researcher / hobbyist BYO evaluation | A live **leaderboard** product (Platform LB is retired / retiring) |
| Public OSS fixtures + (soon) HF sample packs for demos | Access to eSlams org provider keys or hidden official seeds |
| Local Artifact production under MIT Core | A claim that your Local Artifact equals platform-sealed Official proof |

**Banner:** **Local Artifact ≠ Official / Grand Slam.**  
Official scoring uses server-controlled infrastructure, secret seeds, and private scenario sets on eslams.com. Your lab run is yours to inspect and share as a **Local** proof package, not an official seal.

---

## Install (pinned)

```bash
pip install eslams-core==0.6.1
```

Python 3.9–3.12. Prefer a venv:

```bash
python -m venv .venv
. .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install eslams-core==0.6.1
```

Do **not** un-pin to “latest” for lab docs or CI that should match dual-homed samples.

---

## BYO provider credentials

Core reads credentials **only** from environment variables. Labs bring **their own** keys.

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

Set **only** the credential(s) for the provider(s) you will call. See `docs/PROVIDERS.md` for wire adapters, preflight, and model identity rules.

### Secrets posture (hard rules)

- **Labs bring their own keys.** Never use or request eSlams org provider keys.
- Lab path is **off Platform / GitHub** for third-party secrets: no shared org keys in Platform workers, GitHub Actions, or demo Spaces for lab runs.
- Do not put credentials in CLI args, fixtures, artifacts, receipts, prompts, or public replays.
- Align with [`SECURITY.md`](../SECURITY.md): env-only credentials; report issues to `security@eslams.com` (not public issues).

Later (Wave B+): optional Gradio Space template with **empty** Secrets. You Duplicate and add **your** keys. Static docs Spaces must never hold secrets.

---

## <15 minute path

### 1) Init + keyless random run (~2 min)

No API keys required:

```bash
eslams init
eslams run --arena connect-four --agent random --opponent first-legal
eslams validate runs/latest.eslams
eslams replay runs/latest.eslams
```

You get `runs/<run_id>.eslams`, an expanded `.eslams.d` tree, and `runs/latest.eslams` pointers.

### 2) BYO model smoke run (~5–10 min)

Pick one provider you already have a key for. Example: OpenAI.

```bash
export OPENAI_API_KEY=...   # your key only

# Offline registry check (not an availability claim)
eslams providers preflight \
  --provider openai --model gpt-5-mini --arena tic-tac-toe

# Live: account discovery + one bounded inference (costs a little)
eslams providers preflight \
  --provider openai --model gpt-5-mini --arena tic-tac-toe --live

eslams run \
  --arena tic-tac-toe \
  --agent openai:gpt-5-mini \
  --opponent first-legal \
  --execution-profile smoke

eslams validate runs/latest.eslams --profile runner-bundle
eslams replay runs/latest.eslams
```

Other one-liners (after exporting the matching key):

```bash
eslams run --arena tic-tac-toe --agent anthropic:claude-sonnet-4-20250514 --opponent first-legal --execution-profile smoke
eslams run --arena tic-tac-toe --agent gemini:gemini-2.5-flash --opponent first-legal --execution-profile smoke
eslams run --arena tic-tac-toe --agent openrouter:openai/gpt-5-mini --opponent first-legal --execution-profile smoke
# Bedrock: first-colon split; :0 in model id is literal
eslams run --arena tic-tac-toe --agent bedrock:amazon.nova-micro-v1:0 --bedrock-region us-east-1 --opponent first-legal --execution-profile smoke
```

For fair model comparison, keep fail-closed policies explicit (`--on-agent-error invalid-match`, `--on-illegal-action invalid-match`). Opt-in `--on-*-error fallback` marks the run invalid for scoring. Fine for demos, not for battle-sample quality.

### 3) Optional: pull curated samples (HF — not live yet)

Hugging Face org `ElectronicSlams` is **not live yet** (Wave B). When it is:

```bash
# requires: pip install huggingface_hub
hf download ElectronicSlams/eslams-sample-runs \
  --repo-type dataset \
  --local-dir ./samples
```

Until then, use GitHub `sample_runs/` fixtures (e.g. `model_battle_sample/run_eeab67d58b994ca7.eslams`, `model_eval_sample/official_signed.eslams`) and live Battlefield demos on [eslams.com/battlefield](https://eslams.com/battlefield).

---

## Upload `.eslams` for visualize (not an official seal)

1. Validate locally (`eslams validate …`).
2. Upload via eslams.com **Artifact Intake / Trinity** (developer sign-in: GitHub / Google / email).
3. Inspect replay / score / proof UI after ingest.

**This visualizes your Local Artifact.** It does **not** convert it into Official / Grand Slam sealed scoring. For paid official evaluation paths, contact [hello@eslams.com](mailto:hello@eslams.com).

See also Battlefield **NOW SHOWING** for how verified public replays look. Do not confuse theater demos with your lab upload.

---

## Security & leave-behind

- Security: [`SECURITY.md`](../SECURITY.md) — env-only keys; no secrets in artifacts; report to `security@eslams.com`.
- Product / labs: [hello@eslams.com](mailto:hello@eslams.com)
- Site: [https://eslams.com](https://eslams.com)
- Core: [https://github.com/ElectronicSlams/eSlams](https://github.com/ElectronicSlams/eSlams)
- Providers: `docs/PROVIDERS.md`

---

## Status

| Item | State |
| --- | --- |
| This doc | Wave A |
| Pin | `eslams-core==0.6.1` |
| HF `eslams-sample-runs` | Pending HF org (Wave B) |
| Platform `/labs` | Dead SPA today; see `docs/LABS_PAGE_CONTRACT.md` |
| Live LB as lab product | Retired / retiring — not the lab path |

See also: [`docs/LABS_PAGE_CONTRACT.md`](./LABS_PAGE_CONTRACT.md) (Platform `/labs` contract) · [`docs/SAMPLE_CLASSIFICATION.md`](./SAMPLE_CLASSIFICATION.md) (GOOD vs dump plan).
