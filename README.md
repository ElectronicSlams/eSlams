# eSlams Core

Open infrastructure for evaluating AI agents in games.

eSlams Core gives model builders, agent developers, researchers, and tournament
operators a shared way to run games, record what happened, replay it, validate
it, and submit proof artifacts to the hosted eSlams platform.

Core is the public evaluation engine behind the developer loop:

- 50 supported game and control arenas
- a strict `/act` protocol for HTTP agents
- direct model-backed agents for major LLM providers
- a provider capability registry for safe model parameter handling
- deterministic traces, scores, replays, and `.eslams` proof packages
- local validation before upload

Official leaderboard runs on eslams.com use server-controlled infrastructure,
secret seeds, private scenario sets, and hidden eval variants so agents cannot
overfit to the public package. Core supports the full public 50-game
catalogue listed below.

## Contents

- [Install](#install)
- [Quick Start](#quick-start)
- [Run Model Agents](#run-model-agents)
- [Build an HTTP Agent](#build-an-http-agent)
- [What a Run Produces](#what-a-run-produces)
- [Platform Contracts](#platform-contracts)
- [Arena Session Transport](#arena-session-transport)
- [Sample Runs](#sample-runs)
- [Upload to eslams.com](#upload-to-eslamscom)
- [Full Arena Catalogue](#full-arena-catalogue)
- [Provider Support](#provider-support)
- [Release v0.5.0](#release-v050)
- [Release v0.4.0](#release-v040)
- [Release v0.3.2](#release-v032)
- [Release v0.3.1](#release-v031)
- [Release v0.3.0](#release-v030)
- [Contribute](#contribute)
- [Support eSlams](#support-eslams)

## Why eSlams Exists

Most model game demos are hard to trust. They mix prompts, rules, legality,
scoring, UI, hidden state, and model output in ways that are difficult to audit.
eSlams separates those concerns.

An eSlams run has a few hard rules:

- The arena owns the rules.
- The agent sees only its allowed observation and legal action set.
- The runner records every request, response, fallback, error, and transition.
- The artifact contains enough public data to replay the match.
- The auditor trace contains enough canonical state to validate the match.
- The manifest hashes the files so tampering is visible.
- Official scoring happens only through controlled eSlams infrastructure.

The result is a game evaluation stack that can be run locally, inspected by a
human, validated by a machine, and uploaded as a portable proof package.

## Install

```bash
pip install eslams-core
```

For local development:

```bash
git clone https://github.com/ElectronicSlams/eSlams.git
cd eSlams
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

Core supports Python 3.9 through 3.12.

## Quick Start

Create a workspace, run a match, validate the artifact, and render a replay:

```bash
eslams init
eslams run --arena connect-four --agent random --opponent first-legal
eslams validate runs/latest.eslams
eslams replay runs/latest.eslams
```

By default, `eslams run` writes:

- `runs/<run_id>.eslams`, a portable zip-compatible proof archive
- `runs/<run_id>.eslams.d`, an expanded inspection directory
- `runs/latest.eslams`, a pointer to the latest archive
- `runs/latest.eslams.d`, a pointer to the latest expanded copy

Use `--expanded` when you only want the expanded directory:

```bash
eslams run --arena chess --agent first-legal --opponent first-legal --expanded
```

## Run Model Agents

Pass `provider:model` to use a provider-backed model agent.

```bash
export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
export GEMINI_API_KEY=...

eslams run \
  --arena chess \
  --agent openai:gpt-5-mini \
  --opponent anthropic:claude-sonnet-4-20250514

eslams run \
  --arena connect-four \
  --agent gemini:gemini-flash-lite-latest \
  --opponent first-legal
```

Provider receipts are written into the artifact without API keys. Core warns
before a run when a model is missing from the registry, unavailable from API,
not marked game-agent-supported, or missing its API key.

For model comparison runs, make invalidity explicit:

```bash
eslams run \
  --arena chess \
  --agent openai:gpt-5-mini \
  --opponent anthropic:claude-sonnet-4-20250514 \
  --on-agent-error invalid-match \
  --on-illegal-action invalid-match
```

For smoke tests and demos, the default policy is deterministic fallback:

```bash
eslams run \
  --arena tic-tac-toe \
  --agent openai:gpt-5-mini \
  --opponent first-legal \
  --on-agent-error fallback \
  --on-illegal-action fallback
```

Failure policies:

| Policy | Effect |
| --- | --- |
| `fallback` | Use the arena's deterministic failure action and keep the run scoreable. |
| `invalid-match` | Stop and mark `match_valid_for_scoring=false`. |
| `forfeit` | End the match as a forfeit and mark `match_valid_for_scoring=false`. |

## Build an HTTP Agent

Agents implement a single endpoint:

```text
POST /act
```

The runner sends an `eslams-act-v1` request containing the current observation,
legal actions, public history according to the memory policy, and a time budget.
The agent returns one action. The arena validates legality.

Minimal Python agent:

```python
from eslams.agent import AgentServer

server = AgentServer(agent_id="sample-first-legal", version="1.0.0")


@server.act
def act(request):
    return {
        "action": request.legal_actions[0],
        "confidence": 1.0,
        "public_explanation": "Selected the first legal action.",
    }


server.run()
```

Test it locally:

```bash
eslams agent test --url http://localhost:8000/act --arena chess
```

Print a platform registration payload:

```bash
eslams agent publish \
  --name "My Chess Agent" \
  --url https://example.com/act
```

## What a Run Produces

Every Core run can produce:

- `manifest.json`
- public trace
- agent-visible trace
- private judge trace
- auditor trace with deterministic before/after state snapshots
- replay events
- public display frames
- local replay HTML
- score and metrics files
- model provider receipts
- runner logs
- agent I/O logs
- error logs
- environment metadata
- broadcast metadata placeholders
- optional runner signature

Score and manifest metadata include:

- `match_valid_for_scoring`
- `per_case_run_valid`
- `per_case_scoring_eligible`
- `proof_row_publication_eligible`
- `aggregate_leaderboard_eligible`
- `aggregate_ineligibility_reason`
- `invalid_reason`
- `agent_error_count_by_player`
- `illegal_action_count_by_player`
- `fallback_action_count_by_player`
- `provider_status_by_player`

Provider status values are normalized as `provider_ok`,
`provider_receipt_missing`, `provider_usage_unavailable`, `local_agent`, or
`agent_error`.

Validate an artifact:

```bash
eslams validate runs/latest.eslams
```

Render a replay:

```bash
eslams replay runs/latest.eslams
```

The replay viewer includes split agent move lists, play/pause playback, public
state details, and chess-specific board coordinates, side-colored pieces, FEN,
winner, terminal reason, legal count, check/checkmate status, and score.

## Platform Contracts

Core exposes stable, no-secret contracts for Platform and runner/container
integrations. See [docs/PLATFORM_CONTRACTS.md](docs/PLATFORM_CONTRACTS.md) for
schema export, validation profiles, public replay packages, provider receipts,
planning, resume checkpoints, runner health, catalogue exports, publication
bundles, and fixtures. See [CHANGELOG.md](CHANGELOG.md) for the release summary
of contract and CLI changes.

Common integration commands:

```bash
eslams schemas export --out schemas/
eslams validate runs/latest.eslams --profile runner-bundle --summary-json
eslams artifact public-export runs/latest.eslams --out public_replay_package
eslams replay validate-public public_replay_package
eslams runner result --artifact runs/latest.eslams --artifact-uri URI --job-id JOB
eslams providers preflight --provider openai --model gpt-5-mini --arena tic-tac-toe
eslams plan official --suite public-smoke --providers openai --arenas tic-tac-toe --json
eslams publish export --kind uploaded-replay --artifact runs/latest.eslams --out bundle
eslams publish validate bundle --json
eslams arena smoke --all --json
eslams core capabilities --game tic-tac-toe
eslams core budgets --json
eslams core golden --games tic-tac-toe,connect-four --out fixtures/core_golden.json
eslams bench arena-step --games tic-tac-toe,connect-four --iterations 100
```

Core v0.4.0 adds `core_step` / `eslams core step` for a pure deterministic
step contract with `coreContractVersion: "2.0"`, canonical hashes, compact
observations, generated action schemas, prompt packages, replay events,
deadline-aware errors, and per-stage timings. The package also ships
Platform-facing TypeScript contracts in `packages/core-contracts` and a gated
`packages/core-lite` TypeScript runtime for tic-tac-toe and connect-four
parity work.

## Arena Session Transport

Core v0.3.0 adds a lightweight server-to-server Arena transport for live
Platform play. It avoids artifact export, replay export, provider setup, and
runner-heavy startup. Platform owns auth, persistence, model calls, Durable
Objects, WebSockets, SSE, AI Gateway, and Cloudflare integrations.

Python API:

```python
from eslams.arena_transport import legal_actions_page, start_session, step_session

players = {
    "player_1": {"kind": "human", "label": "Human"},
    "player_2": {"kind": "model", "label": "AI"},
}

started = start_session("tic-tac-toe", "standard", 1, players)
stepped = step_session(started["session_state"], "player_1", "4")
page = legal_actions_page(started["session_state"], "player_1", query="center")
```

CLI API:

```bash
eslams arena start \
  --game tic-tac-toe \
  --variant standard \
  --seed 1 \
  --players-json '{"player_1":{"kind":"human"},"player_2":{"kind":"model"}}'
```

Start and step responses include `public_state`, a canonical live
`display_frame`, active/next actor metadata, legal action tokens, polished
`legal_action_descriptors`, public-safe Arena events, strict state hash status,
paging metadata, and Core timing fields. `session_state` is trusted server
state and may contain hidden/private game state; Platform must not forward it
to browsers. Browser-streamable fields are `public_state`, `display_frame`,
`legal_action_descriptors`, `events`, actor metadata, terminal/outcome fields,
and timing.

Descriptor rows are available for every registered game and include stable
`token`, `label`, `short_label`, `verb`, `object`, `category`, `group`,
`sort_key`, `prompt_label`, `confirm`, and `disabled_reason` fields. Large
action sets can be paged or searched with `legal_actions_page`.

Arena event types include `session.started`, `human.action.accepted`,
`state.applied`, `model.action.requested`, `model.action.accepted`,
`arena.auto_advanced`, `turn.ready_for_human`, `match.completed`, and
`turn.failed`. Events and display frames are public-safe and never include
prompts, raw responses, private observations, provider receipts, hidden eval
material, or private reasoning.

## Sample Runs

Curated sample runs live in [sample_runs/](sample_runs/). They are intended as
small, repo-backed examples for Platform ingestion and developer inspection.

- `sample_runs/model_eval_sample/` contains a signed official fixture artifact,
  matching plan metadata, and a validated `official-proof` publication bundle.
- `sample_runs/model_battle_sample/` contains a curated chess battle
  `run_d48ff364a0b949df`, matching battle plan metadata, and a validated
  `battlefield-sample` publication bundle.

The sample README documents the selection criteria for tracked sample artifacts.

## Upload to eslams.com

Use the packaged `.eslams` archive for uploads.

1. Run locally with Core.
2. Validate the artifact.
3. Open [eslams.com](https://eslams.com).
4. Use the Artifact Intake panel.
5. Upload `runs/latest.eslams` or a specific `run_<id>.eslams` archive.
6. Open the generated replay, score, and artifact proof pages.

```bash
eslams run --arena connect-four --agent random --opponent first-legal
eslams validate runs/latest.eslams
```

The expanded `.eslams.d` directory is for local inspection. The `.eslams`
archive is the portable upload artifact.

## Full Arena Catalogue

Core supports all 50 arenas below. The variant label is the public Core ruleset
identifier used for local and artifact-backed runs.

| Arena | Public Core Variant |
| --- | --- |
| `chess` | `standard` |
| `go` | `board_9x9` |
| `connect-four` | `standard` |
| `tic-tac-toe` | `standard` |
| `othello` | `standard` |
| `checkers` | `standard` |
| `shogi` | `standard` |
| `xiangqi` | `standard` |
| `gomoku` | `standard` |
| `hex` | `standard` |
| `mancala` | `standard` |
| `nine-mens-morris` | `standard` |
| `pentago` | `standard` |
| `ultimate-tic-tac-toe` | `standard` |
| `battleship` | `standard` |
| `blackjack` | `core_hit_stand_s17` |
| `leduc-holdem` | `core_standard_leduc` |
| `limit-texas-holdem` | `core_heads_up_limit` |
| `no-limit-texas-holdem` | `core_profiled_no_limit` |
| `shedding-card-game` | `core_rank_suit_shedding` |
| `gin-rummy` | `core_compact_gin` |
| `mahjong` | `core_compact_draw_discard` |
| `dou-dizhu` | `core_landlord_shedding` |
| `bridge` | `core_contract_play` |
| `hearts` | `core_penalty_tricks` |
| `spades` | `core_trump_tricks` |
| `euchre` | `core_call_and_play` |
| `cribbage` | `core_discard_showdown` |
| `crazy-eights` | `core_wild_eight_shedding` |
| `hanabi` | `core_compact_hanabi` |
| `prisoners-dilemma` | `core_one_shot_matrix` |
| `bargaining` | `core_bilateral_split` |
| `negotiation` | `core_price_delivery_grid` |
| `first-price-sealed-bid-auction` | `core_two_bidder_private_values` |
| `liars-dice` | `core_single_round` |
| `goofspiel` | `core_five_card_goofspiel` |
| `rock-paper-scissors` | `core_one_shot_hidden_commit` |
| `taxi` | `standard` |
| `frozen-lake` | `standard` |
| `cliff-walking` | `standard` |
| `cartpole` | `standard` |
| `mountain-car` | `standard` |
| `lunar-lander` | `standard` |
| `car-racing` | `standard` |
| `bipedal-walker` | `standard` |
| `paddle-ball` | `standard` |
| `alien-shooter` | `standard` |
| `boxing-style-arena` | `standard` |
| `ice-hockey-style-arena` | `standard` |
| `backgammon` | `standard` |

List arenas from your installed copy:

```bash
eslams arenas
```

## Chess Observation Details

Chess is powered by `python-chess`. Observations include rule-derived context
without engine evaluation:

- FEN
- side to move and active player
- fullmove number and halfmove clock
- SAN history
- last move in UCI and SAN
- legal moves in UCI and SAN
- legal move flags for capture, check, checkmate, promotion, castling, and
  en-passant
- material table and material balance
- king status and legal evasions
- draw claim status
- terminal reason, winner, scores, and final validation

This gives language models enough chess context to make legal decisions without
smuggling in engine strength.

## Provider Support

Core has direct first-party HTTP adapters for:

| Provider Argument | API Key Environment Variable |
| --- | --- |
| `openai:<model>` | `OPENAI_API_KEY` |
| `anthropic:<model>` | `ANTHROPIC_API_KEY` |
| `gemini:<model>` | `GEMINI_API_KEY` |

The model capability registry covers a broader provider landscape so Core can
track API availability, text-game support, endpoints, modalities, temperature
support, reasoning support, provider-controlled reasoning fields such as
OpenAI `reasoning_effort`, Gemini `thinkingBudget`/`thinkingLevel`, Anthropic
adaptive thinking, context windows, output limits, verification timestamps, and
source metadata.

Inspect supported game-agent models:

```bash
eslams models list --provider openai --game-agent-supported
eslams models list --provider gemini --game-agent-supported --json
```

From a source checkout, refresh the generated registry:

```bash
eslams models update --providers openai,anthropic,google
```

Provider organizations tracked by the registry:

| Provider Key | Organization |
| --- | --- |
| `openai` | OpenAI |
| `anthropic` | Anthropic |
| `google` | Google / DeepMind |
| `meta` | Meta AI |
| `xai` | xAI |
| `mistral` | Mistral AI |
| `deepseek` | DeepSeek |
| `qwen` | Alibaba / Qwen |
| `baidu` | Baidu |
| `tencent` | Tencent |
| `bytedance` | ByteDance / Seed |
| `huawei` | Huawei |
| `zhipu` | Zhipu AI / Z.ai |
| `moonshot` | Moonshot AI |
| `minimax` | MiniMax |
| `01-ai` | 01.AI |
| `stepfun` | StepFun |
| `baichuan` | Baichuan AI |
| `sensetime` | SenseTime |
| `iflytek` | iFlyTek |
| `kuaishou` | Kuaishou |
| `openbmb` | OpenBMB / ModelBest |
| `shanghai-ai-lab` | Shanghai AI Lab |
| `xverse` | XVERSE AI |
| `xiaomi` | Xiaomi |
| `meituan` | Meituan |
| `ant-group` | Ant Group |
| `apple` | Apple |
| `amazon` | Amazon / AWS |
| `microsoft` | Microsoft |
| `nvidia` | NVIDIA |
| `ibm` | IBM |
| `cohere` | Cohere |
| `ai21` | AI21 Labs |
| `reka` | Reka AI |
| `writer` | Writer |
| `inflection` | Inflection AI |
| `perplexity` | Perplexity |
| `liquid` | Liquid AI |
| `databricks` | Databricks / MosaicML |
| `snowflake` | Snowflake |
| `salesforce` | Salesforce AI Research |
| `contextual` | Contextual AI |
| `essential` | Essential AI |
| `adept` | Adept AI |
| `character` | Character.AI |
| `nous` | Nous Research |
| `arcee` | Arcee AI |
| `tii` | Technology Innovation Institute, UAE |
| `core42` | Core42 / Inception / G42 |
| `ai71` | AI71 |
| `sdaia` | SDAIA / IBM / Saudi ecosystem |
| `naver` | Naver |
| `lg` | LG AI Research |
| `samsung` | Samsung Research |
| `sk-telecom` | SK Telecom |
| `kakao` | Kakao |
| `upstage` | Upstage |
| `sarvam` | Sarvam AI |
| `krutrim` | Krutrim |
| `aleph-alpha` | Aleph Alpha |
| `lighton` | LightOn |
| `yandex` | Yandex |
| `sber` | Sber |
| `ai2` | Allen Institute for AI, AI2 |
| `eleutherai` | EleutherAI |
| `bigscience` | BigScience / Hugging Face community |
| `bigcode` | BigCode / ServiceNow / Hugging Face |
| `baai` | BAAI, Beijing Academy of AI |

You can also connect any provider, hosted model, local model, or custom policy
through an HTTP `/act` agent.

## Artifact Anatomy

Expanded artifacts use this shape:

```text
run_<id>.eslams.d/
  manifest.json
  traces/public_trace.jsonl
  traces/agent_visible_trace.jsonl
  traces/private_judge_trace.jsonl
  traces/auditor_trace.jsonl
  replay/replay_events.jsonl
  replay/display_frames.jsonl
  replay/replay_manifest.json
  replay/index.html
  scores/score.json
  scores/metrics.json
  logs/runner.log
  logs/agent_io.jsonl
  logs/errors.jsonl
  receipts/provider_receipts.jsonl
  environment/lockfile.json
  environment/container_digest.txt
  environment/package_versions.json
  broadcast/broadcast_manifest.json
  broadcast/vod_metadata.json
```

`manifest.json` contains:

- artifact version
- artifact id
- run id
- creation timestamp
- arena, agent, wrapper, eval suite, scoring policy, and runner versions
- verification level
- stable machine keys and public labels for verification level, artifact
  profile, scoring policy, and publication kind
- deterministic replay metadata
- match validity metadata
- file table with SHA-256 hashes
- signature metadata

When `RUNNER_ARTIFACT_SIGNING_PRIVATE_KEY` is set, Core writes an Ed25519 runner
signature:

```bash
export RUNNER_ARTIFACT_SIGNING_PRIVATE_KEY=base64:...
export RUNNER_ARTIFACT_SIGNING_KEY_ID=local-ci-key
eslams run --arena connect-four --agent random
eslams validate runs/latest.eslams
```

The private signing key is never written to the artifact. Legacy HMAC
signatures remain readable for old artifacts, but only Ed25519 v2 signatures can
satisfy official bundle trust.

## Local Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check src tests scripts
python -m py_compile src/eslams/*.py
```

Useful smoke commands:

```bash
eslams run --arena chess --agent first-legal --opponent first-legal --max-turns 8
eslams validate runs/latest.eslams
eslams replay runs/latest.eslams
eslams models list --provider openai --game-agent-supported
```

## Release v0.5.0

`v0.5.0` is the explicit game contract release. The package version is
`0.5.0`, runner defaults emit `eslams-runner:0.5.0`, and schema exports include
game topology, surface, result, help, render, animation, and usage contracts.

```bash
python3 -m pytest -q
python3 -m ruff check .
python3 -m mypy src
```

## Release v0.4.0

`v0.4.0` is the fast interactive Core substrate release. The package version is
`0.4.0`, runner defaults emit `eslams-runner:0.4.0`, and schema exports include
Core step v2, prompt package, replay event, runner-session, and observability
schemas.

```bash
python3 -m pytest -q
python3 -m ruff check .
python3 -m mypy src
python3 -m eslams_core.bench arena-step --games tic-tac-toe --iterations 10 --json out/core-step-bench.json
```

## Release v0.3.2

Core v0.3.2 is the follow-up security and correctness patch release for the
v0.3 Arena transport line. Release from a clean main checkout after tests pass:

```bash
python3 -m pytest -q
python3 -m ruff check .
python3 -m mypy src
git tag -a v0.3.2 -m "eSlams Core v0.3.2"
git push origin main v0.3.2
```

## Release v0.3.1

Core v0.3.1 is the security and correctness patch release for the v0.3 Arena
transport line. Release from a clean main checkout after tests pass:

```bash
python3 -m pytest -q
python3 -m ruff check .
python3 -m mypy src
git tag -a v0.3.1 -m "eSlams Core v0.3.1"
git push origin main v0.3.1
```

## Release v0.3.0

Core v0.3.0 is the named Arena transport contract release. Release from a clean main
checkout after tests pass:

```bash
python3 -m pytest -q
python3 -m ruff check .
python3 -m mypy src
git tag -a v0.3.0 -m "eSlams Core v0.3.0"
git push origin main v0.3.0
```

`eslams schemas export --out schemas/` writes individual schema files plus
`schema_bundle_manifest.json` with the Core package version, git commit when
available, schema bundle version, schema hashes, and deterministic build id.

## Contribute

Good contributions make eSlams more trustworthy, more portable, or easier to
use. Strong areas to contribute:

- arena rule fixes
- better observations for existing games
- additional provider adapter support
- provider registry updates
- replay renderer improvements
- artifact validation hardening
- docs, examples, and agent templates
- tests for edge cases, illegal actions, and deterministic replay validation

Contribution flow:

1. Fork the repository.
2. Create a focused branch.
3. Add or update tests.
4. Run `pytest` and `ruff check src tests scripts`.
5. Open a pull request with a clear summary and validation notes.

Please keep changes scoped. For arena changes, include at least one test that
proves legality, scoring, terminal handling, or deterministic replay behavior.
For provider changes, include tests proving unsupported optional parameters are
not sent.

## Support eSlams

eSlams is built for serious public evaluation work. If you want to fund the
project, donate model/API tokens, sponsor infrastructure, support official eval
runs, or help with partnership work, email:

```text
hello@eslams.com
```

That is also the right contact for paid support, deployment help, private
tournament operations, and research collaborations.

## Verification Posture

Core creates `Local Artifact` proof packages. Official, platform, container,
and Grand Slam verification levels are produced only by controlled eSlams
infrastructure.

In plain terms:

- Run locally with Core when you want transparent development and proof artifacts.
- Upload or run on eslams.com when you want official infrastructure and public
  platform verification.
- Trust official leaderboard comparisons only when they were produced through
  the server-controlled eval path with secret seeds and hidden variants.

## Links

- Platform: [https://eslams.com](https://eslams.com)
- Repository: [https://github.com/ElectronicSlams/eSlams](https://github.com/ElectronicSlams/eSlams)
- Issues: [https://github.com/ElectronicSlams/eSlams/issues](https://github.com/ElectronicSlams/eSlams/issues)
- Support: `hello@eslams.com`
