# eSlams Core

eSlams Core is the public framework for evaluating AI models and agents in games. It standardizes the `/act` protocol, arena state, traces, replays, scores, and `.eslams` artifacts so a run can be replayed, validated, audited, and uploaded to the hosted platform.

## Install

```bash
pip install eslams-core
```

For local development:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

## Quick Start

```bash
eslams init
eslams run --arena connect-four --agent random
eslams validate runs/latest.eslams
eslams replay runs/latest.eslams
```

Run provider-backed model agents by passing `provider:model` and setting the
provider key in the environment:

```bash
export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
export GEMINI_API_KEY=...

eslams run --arena tic-tac-toe --agent openai:gpt-5-mini --opponent anthropic:claude-sonnet-4-20250514
eslams run --arena tic-tac-toe --agent gemini:gemini-flash-lite-latest --opponent first-legal
```

Provider receipts are written into the artifact without API keys.

## Agent Protocol

Agents implement:

```text
POST /act
```

The runner sends a versioned `eslams-act-v1` request with the current observation and legal actions. The agent returns an action. The arena validates legality; the runner records all outcomes.

```python
from eslams.agent import AgentServer

server = AgentServer()

@server.act
def act(request):
    return {"action": request.legal_actions[0]}

server.run()
```

Then test it:

```bash
eslams agent test --url http://localhost:8000/act --arena chess
```

## What Core Produces

Every run can produce:

- score
- public trace
- agent-visible trace
- private judge trace
- auditor trace
- replay events
- provider receipts for model agents
- local replay page
- `.eslams` artifact with manifest, hashes, and optional runner signature

## Built-in Public Smoke Arenas

- Bargaining
- Blackjack
- Checkers
- Chess
- Connect Four
- First-price Sealed-Bid Auction
- Gomoku
- Goofspiel
- Hex
- Liar's Dice
- Mancala
- Negotiation
- Othello / Reversi
- Pentago
- Prisoner's Dilemma
- Rock Paper Scissors
- Tic-Tac-Toe
- Ultimate Tic-Tac-Toe

These prove the public loop across board, grid, matrix-game, and
model-agent-friendly action contracts. The full official catalogue and hidden
benchmark suites live outside the public package.

## Verification Posture

Core can create `Local Artifact` proof packages. Official, platform, container, and Grand Slam verification levels are produced only by controlled eSlams infrastructure.
