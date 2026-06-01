"""eSlams command line interface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from eslams.agents import HttpAgent
from eslams.arena import registry
from eslams.arenas import ChessArena, ConnectFourArena, TicTacToeArena  # noqa: F401
from eslams.artifacts import ArtifactValidator
from eslams.protocol import ActRequest
from eslams.replay import render_replay_html
from eslams.runner import RunConfig, Runner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="eslams",
        description="Run, validate, and replay eSlams artifacts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create a local eSlams workspace.")

    sub.add_parser("arenas", help="List built-in arenas.")

    run = sub.add_parser("run", help="Run a local match and create a .eslams artifact.")
    run.add_argument("--arena", default="connect-four", choices=registry.list())
    run.add_argument(
        "--agent",
        default="random",
        help="Agent for player_1: random, first-legal, or URL.",
    )
    run.add_argument(
        "--opponent",
        default="first-legal",
        help="Agent for player_2: random, first-legal, or URL.",
    )
    run.add_argument("--seed", type=int, default=1)
    run.add_argument("--output-dir", type=Path, default=Path("runs"))
    run.add_argument("--archive", action="store_true")

    validate = sub.add_parser("validate", help="Validate an artifact directory or .eslams zip.")
    validate.add_argument("artifact", type=Path)

    replay = sub.add_parser("replay", help="Render a local HTML replay from an artifact.")
    replay.add_argument("artifact", type=Path)
    replay.add_argument("--output", type=Path)

    agent = sub.add_parser("agent", help="Agent helper commands.")
    agent_sub = agent.add_subparsers(dest="agent_command", required=True)
    agent_test = agent_sub.add_parser("test", help="Protocol-test a remote /act endpoint.")
    agent_test.add_argument("--url", required=True)
    agent_test.add_argument("--arena", default="tic-tac-toe", choices=registry.list())
    agent_test.add_argument("--seed", type=int, default=1)
    agent_publish = agent_sub.add_parser("publish", help="Print a platform registration payload.")
    agent_publish.add_argument("--name", required=True)
    agent_publish.add_argument("--url", required=True)
    agent_serve = agent_sub.add_parser("serve", help="Serve a sample first-legal /act endpoint.")
    agent_serve.add_argument("--host", default="0.0.0.0")
    agent_serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)
    if args.command == "init":
        Path("runs").mkdir(exist_ok=True)
        Path("agents").mkdir(exist_ok=True)
        print("Created runs/ and agents/. Try: eslams run --arena connect-four --agent random")
        return 0
    if args.command == "arenas":
        for arena_id in registry.list():
            print(arena_id)
        return 0
    if args.command == "run":
        result = Runner().run(
            RunConfig(
                arena_id=args.arena,
                agent_1=_agent_arg(args.agent),
                agent_2=_agent_arg(args.opponent),
                seed=args.seed,
                output_dir=args.output_dir,
                archive=args.archive,
            )
        )
        print(
            json.dumps(
                {
                    "run_id": result.run_id,
                    "artifact": str(result.artifact_path),
                    "score": result.score.to_dict(),
                },
                indent=2,
            )
        )
        return 0
    if args.command == "validate":
        errors = ArtifactValidator().validate(args.artifact)
        if errors:
            print(json.dumps({"valid": False, "errors": errors}, indent=2))
            return 1
        print(json.dumps({"valid": True, "artifact": str(args.artifact)}, indent=2))
        return 0
    if args.command == "replay":
        output = render_replay_html(args.artifact, args.output)
        print(json.dumps({"replay": str(output)}, indent=2))
        return 0
    if args.command == "agent":
        return _agent_command(args)
    raise AssertionError(args.command)


def _agent_arg(value: str) -> str | HttpAgent:
    if value.startswith("http://") or value.startswith("https://"):
        return HttpAgent(url=value)
    return value


def _agent_command(args: argparse.Namespace) -> int:
    if args.agent_command == "test":
        result = Runner().run(
            RunConfig(
                arena_id=args.arena,
                agent_1=HttpAgent(url=args.url, id="protocol-test-agent", version="test"),
                agent_2="first-legal",
                seed=args.seed,
                max_turns=2,
                output_dir=Path("runs/protocol-tests"),
            )
        )
        print(
            json.dumps(
                {"ok": True, "run_id": result.run_id, "artifact": str(result.artifact_path)},
                indent=2,
            )
        )
        return 0
    if args.agent_command == "publish":
        print(
            json.dumps(
                {
                    "name": args.name,
                    "connection": {
                        "type": "http",
                        "endpoint": args.url,
                        "protocol": "eslams-act-v1",
                    },
                    "verification_level": "Community Validated",
                },
                indent=2,
            )
        )
        return 0
    if args.agent_command == "serve":
        from eslams.agent import AgentServer

        server = AgentServer(agent_id="sample-first-legal", version="1.0.0")

        @server.act
        def act(request: ActRequest) -> dict[str, Any]:
            return {"action": request.legal_actions[0], "confidence": 1.0}

        server.run(host=args.host, port=args.port)
        return 0
    raise AssertionError(args.agent_command)


if __name__ == "__main__":
    raise SystemExit(main())
