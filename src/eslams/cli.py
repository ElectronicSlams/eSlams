"""eSlams command line interface."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import eslams.arenas  # noqa: F401
from eslams.agents import HttpAgent, ModelProviderAgent
from eslams.arena import registry
from eslams.artifacts import ArtifactValidator
from eslams.protocol import ActRequest
from eslams.providers import load_provider_registry
from eslams.replay import render_replay_html
from eslams.runner import FAILURE_POLICIES, RunConfig, Runner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="eslams",
        description="Run, validate, and replay eSlams artifacts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create a local eSlams workspace.")

    sub.add_parser("arenas", help="List built-in arenas.")

    models = sub.add_parser("models", help="Inspect or refresh provider model capabilities.")
    models_sub = models.add_subparsers(dest="models_command", required=True)
    models_list = models_sub.add_parser("list", help="List registry models.")
    models_list.add_argument("--provider")
    models_list.add_argument("--game-agent-supported", action="store_true")
    models_list.add_argument("--json", action="store_true")
    models_update = models_sub.add_parser(
        "update",
        help="Refresh generated provider registry data.",
    )
    models_update.add_argument("--providers", default="")
    models_update.add_argument("--skip-public", action="store_true")

    run = sub.add_parser("run", help="Run a local match and create a .eslams artifact.")
    run.add_argument("--arena", default="connect-four", choices=registry.list())
    run.add_argument(
        "--agent",
        default="random",
        help="Agent for player_1: random, first-legal, URL, or provider:model.",
    )
    run.add_argument(
        "--opponent",
        default="first-legal",
        help="Agent for player_2: random, first-legal, URL, or provider:model.",
    )
    run.add_argument("--seed", type=int, default=1)
    run.add_argument("--max-turns", type=int)
    run.add_argument(
        "--time-budget-ms",
        type=int,
        default=30_000,
        help="Per-action agent time budget in milliseconds.",
    )
    run.add_argument("--output-dir", type=Path, default=Path("runs"))
    run.add_argument(
        "--archive",
        dest="archive",
        action="store_true",
        default=True,
        help="Write a packaged .eslams archive (default).",
    )
    run.add_argument(
        "--expanded",
        dest="archive",
        action="store_false",
        help="Write an expanded .eslams.d artifact directory.",
    )
    run.add_argument(
        "--on-agent-error",
        choices=sorted(FAILURE_POLICIES),
        default="fallback",
    )
    run.add_argument(
        "--on-illegal-action",
        choices=sorted(FAILURE_POLICIES),
        default="fallback",
    )
    run.add_argument("--verification-level", default="Local Artifact")
    run.add_argument("--eval-suite-version", default="public-smoke:1.0.0")
    run.add_argument("--runner-version", default="eslams-runner:0.1.0")

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
    if args.command == "models":
        return _models_command(args)
    if args.command == "run":
        agent_1 = _agent_arg(args.agent)
        agent_2 = _agent_arg(args.opponent)
        _print_run_preflight(args, agent_1, agent_2)
        result = Runner().run(
            RunConfig(
                arena_id=args.arena,
                agent_1=agent_1,
                agent_2=agent_2,
                seed=args.seed,
                max_turns=args.max_turns,
                time_budget_ms=args.time_budget_ms,
                output_dir=args.output_dir,
                archive=args.archive,
                on_agent_error=args.on_agent_error,
                on_illegal_action=args.on_illegal_action,
                verification_level=args.verification_level,
                eval_suite_version=args.eval_suite_version,
                runner_version=args.runner_version,
            )
        )
        print(
            json.dumps(
                {
                    "run_id": result.run_id,
                    "artifact": str(result.artifact_path),
                    "expanded_artifact": str(result.expanded_path),
                    "summary": {
                        "winner": result.score.winner,
                        "terminal_reason": _terminal_reason(result),
                        "match_valid_for_scoring": result.score.match_valid_for_scoring,
                        "invalid_reason": result.score.invalid_reason,
                    },
                    "score": result.score.to_dict(),
                },
                indent=2,
            )
        )
        return 0
    if args.command == "validate":
        report = ArtifactValidator().validate_report(args.artifact)
        payload = report.to_dict()
        payload["artifact"] = str(args.artifact)
        if report.errors:
            print(json.dumps(payload, indent=2))
            return 1
        print(json.dumps(payload, indent=2))
        return 0
    if args.command == "replay":
        output = render_replay_html(args.artifact, args.output)
        print(json.dumps({"replay": str(output)}, indent=2))
        return 0
    if args.command == "agent":
        return _agent_command(args)
    raise AssertionError(args.command)


def _agent_arg(value: str) -> str | HttpAgent | ModelProviderAgent:
    if value.startswith("http://") or value.startswith("https://"):
        return HttpAgent(url=value)
    provider = _provider_agent(value)
    if provider is not None:
        return provider
    return value


def _models_command(args: argparse.Namespace) -> int:
    registry = load_provider_registry()
    if args.models_command == "list":
        supported_filter = True if args.game_agent_supported else None
        records = registry.list_models(
            provider=args.provider,
            game_agent_supported=supported_filter,
        )
        if args.json:
            print(json.dumps([record.to_dict() for record in records], indent=2))
            return 0
        for record in records:
            api = (
                "unknown"
                if record.available_from_api is None
                else str(record.available_from_api).lower()
            )
            print(
                f"{record.provider}:{record.model} "
                f"game_agent_supported={str(record.allows_text_game_agent()).lower()} "
                f"available_from_api={api} "
                f"temperature={str(record.supports_temperature).lower()} "
                f"reasoning={str(record.supports_reasoning).lower()}"
            )
        return 0
    if args.models_command == "update":
        return _run_registry_update(args)
    raise AssertionError(args.models_command)


def _run_registry_update(args: argparse.Namespace) -> int:
    script = Path(__file__).resolve().parents[2] / "scripts" / "update_provider_registry.py"
    if not script.exists():
        print(
            "Provider registry updater script is unavailable in this installation.",
            file=sys.stderr,
        )
        return 1
    command = [sys.executable, str(script)]
    if args.providers:
        command.extend(["--providers", args.providers])
    if args.skip_public:
        command.append("--skip-public")
    return subprocess.call(command)


def _provider_agent(value: str) -> ModelProviderAgent | None:
    defaults = {
        "openai": ("gpt-5-mini", "OPENAI_API_KEY"),
        "anthropic": ("claude-sonnet-4-20250514", "ANTHROPIC_API_KEY"),
        "gemini": ("gemini-flash-lite-latest", "GEMINI_API_KEY"),
    }
    if ":" in value:
        provider, model = value.split(":", 1)
    else:
        provider, model = value, ""
    provider = provider.lower()
    if provider not in defaults:
        return None
    default_model, env_name = defaults[provider]
    return ModelProviderAgent(
        provider=provider,
        model=model or default_model,
        api_key_env=env_name,
        version=model or default_model,
    )


def _print_run_preflight(
    args: argparse.Namespace,
    agent_1: str | HttpAgent | ModelProviderAgent,
    agent_2: str | HttpAgent | ModelProviderAgent,
) -> None:
    max_turns = args.max_turns if args.max_turns is not None else "arena-default"
    mode = "archive" if args.archive else "expanded"
    print(
        "Running eSlams "
        f"arena={args.arena} max_turns={max_turns} "
        f"agent_1={_agent_label(agent_1)} agent_2={_agent_label(agent_2)} "
        f"artifact={mode}",
        file=sys.stderr,
    )
    for agent in (agent_1, agent_2):
        if isinstance(agent, ModelProviderAgent):
            _print_provider_warnings(agent)


def _print_provider_warnings(agent: ModelProviderAgent) -> None:
    registry = load_provider_registry()
    for warning in registry.warnings_for(agent.provider, agent.model):
        print(f"warning: {warning}", file=sys.stderr)
    if not os.getenv(agent.api_key_env):
        print(
            f"warning: missing API key {agent.api_key_env} for {agent.provider}:{agent.model}",
            file=sys.stderr,
        )


def _agent_label(agent: str | HttpAgent | ModelProviderAgent) -> str:
    if isinstance(agent, ModelProviderAgent):
        return f"{agent.provider}:{agent.model}"
    if isinstance(agent, HttpAgent):
        return agent.url
    return str(agent)


def _terminal_reason(result: Any) -> str | None:
    if result.score.outcome:
        reason = result.score.outcome.get("reason")
        if isinstance(reason, str):
            return reason
    if result.replay_events:
        terminal_reason = result.replay_events[-1].public_state.get("terminal_reason")
        if isinstance(terminal_reason, str):
            return terminal_reason
    return None


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
