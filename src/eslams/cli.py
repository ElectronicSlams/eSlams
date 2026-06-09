"""eSlams command line interface."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import eslams.arenas  # noqa: F401
from eslams.agents import HttpAgent, ModelProviderAgent
from eslams.arena import registry
from eslams.arena_transport import legal_actions_page, smoke_all_arenas, start_session, step_session
from eslams.artifacts import ArtifactValidator
from eslams.catalogue import availability_rows, game_catalogue_rows, model_catalogue_rows
from eslams.contracts.json_schema import export_schemas
from eslams.eval_runtime import (
    ResumeInvariant,
    append_progress_event,
    load_resume_checkpoint,
    progress_event,
    should_skip_case,
)
from eslams.fixtures import ARTIFACT_FIXTURE_KINDS, create_artifact_fixture
from eslams.official import merge_official_results
from eslams.planning import battlefield_plan, official_plan, public_match_plan
from eslams.protocol import ActRequest
from eslams.provider_preflight import provider_preflight
from eslams.providers import load_provider_registry
from eslams.public_replay import (
    create_uploaded_smoke_fixture,
    export_public_replay,
    validate_public_replay,
)
from eslams.publication_export import export_publication_bundle, validate_publication_bundle
from eslams.rendering import renderer_vocabulary_rows
from eslams.replay import render_replay_html
from eslams.runner import FAILURE_POLICIES, RunConfig, Runner
from eslams.runner_health import current_runner_health
from eslams.runner_result import runner_job_result_from_artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="eslams",
        description="Run, validate, and replay eSlams artifacts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create a local eSlams workspace.")

    sub.add_parser("arenas", help="List built-in arenas.")

    arena = sub.add_parser("arena", help="Arena transport helper commands.")
    arena_sub = arena.add_subparsers(dest="arena_command", required=True)
    arena_smoke = arena_sub.add_parser("smoke", help="Smoke-test stateless arena transport.")
    arena_smoke.add_argument("--all", action="store_true", dest="all_arenas")
    arena_smoke.add_argument("--json", action="store_true")
    arena_start = arena_sub.add_parser("start", help="Start an interactive Arena session.")
    arena_start.add_argument("--game", required=True, choices=registry.list())
    arena_start.add_argument("--variant")
    arena_start.add_argument("--seed", type=int, default=1)
    arena_start.add_argument("--players-json", required=True)
    arena_start.add_argument("--options-json", default="{}")
    arena_step = arena_sub.add_parser("step", help="Apply one action token to a session.")
    arena_step.add_argument("--state", type=Path, required=True)
    arena_step.add_argument("--player-id", required=True)
    arena_step.add_argument("--action-token", required=True)
    arena_page = arena_sub.add_parser(
        "legal-actions-page",
        help="Page/search legal action descriptors for a session.",
    )
    arena_page.add_argument("--state", type=Path, required=True)
    arena_page.add_argument("--player-id", required=True)
    arena_page.add_argument("--query")
    arena_page.add_argument("--limit", type=int, default=50)
    arena_page.add_argument("--cursor")

    schemas = sub.add_parser("schemas", help="Export versioned contract schemas.")
    schemas_sub = schemas.add_subparsers(dest="schemas_command", required=True)
    schemas_export = schemas_sub.add_parser("export", help="Write JSON schema files.")
    schemas_export.add_argument("--out", type=Path, required=True)

    artifact = sub.add_parser("artifact", help="Artifact helper commands.")
    artifact_sub = artifact.add_subparsers(dest="artifact_command", required=True)
    artifact_public = artifact_sub.add_parser(
        "public-export",
        help="Export a no-secret public replay package.",
    )
    artifact_public.add_argument("artifact", type=Path)
    artifact_public.add_argument("--out", type=Path, required=True)

    fixtures = sub.add_parser("fixtures", help="Generate deterministic fixtures.")
    fixtures_sub = fixtures.add_subparsers(dest="fixtures_command", required=True)
    fixtures_replay = fixtures_sub.add_parser("replay", help="Generate replay fixtures.")
    fixtures_replay.add_argument("--kind", choices=["uploaded-smoke"], required=True)
    fixtures_replay.add_argument("--out", type=Path, required=True)
    fixtures_artifact = fixtures_sub.add_parser("artifact", help="Generate artifact fixtures.")
    fixtures_artifact.add_argument("--kind", choices=list(ARTIFACT_FIXTURE_KINDS), required=True)
    fixtures_artifact.add_argument("--out", type=Path, required=True)

    catalogue = sub.add_parser("catalogue", help="Export public catalogue rows.")
    catalogue_sub = catalogue.add_subparsers(dest="catalogue_command", required=True)
    for name in ("games", "models", "availability", "renderers"):
        command = catalogue_sub.add_parser(name, help=f"Export {name} catalogue rows.")
        command.add_argument("--json", action="store_true")

    plan = sub.add_parser("plan", help="Create deterministic no-secret eval plans.")
    plan_sub = plan.add_subparsers(dest="plan_command", required=True)
    plan_official = plan_sub.add_parser("official", help="Plan an official eval suite.")
    plan_official.add_argument("--suite", required=True)
    plan_official.add_argument("--providers", default="")
    plan_official.add_argument("--arenas", default="")
    plan_official.add_argument("--shard-count", type=int, default=1)
    plan_official.add_argument("--json", action="store_true")
    plan_battlefield = plan_sub.add_parser("battlefield", help="Plan Battlefield cases.")
    plan_battlefield.add_argument("--pairs", default="")
    plan_battlefield.add_argument("--arenas", default="")
    plan_battlefield.add_argument("--shard-count", type=int, default=1)
    plan_battlefield.add_argument("--json", action="store_true")
    plan_public = plan_sub.add_parser("public-match", help="Plan a public match request.")
    plan_public.add_argument("--request", type=Path, required=True)
    plan_public.add_argument("--shard-count", type=int, default=1)
    plan_public.add_argument("--json", action="store_true")
    plan_progress = plan_sub.add_parser("progress", help="Append a progress JSONL event.")
    plan_progress.add_argument("--plan", type=Path, required=True)
    plan_progress.add_argument("--out", type=Path, required=True)
    plan_progress.add_argument("--current-case")
    plan_progress.add_argument("--completed-cases", type=int, default=0)
    plan_progress.add_argument("--failed-cases", type=int, default=0)
    plan_progress.add_argument("--skipped-cases", type=int, default=0)
    plan_progress.add_argument("--elapsed-seconds", type=float, default=0.0)
    plan_progress.add_argument("--provider-latencies-ms", default="")
    plan_resume = plan_sub.add_parser("resume-check", help="Check if a case can be skipped.")
    plan_resume.add_argument("--checkpoint", type=Path, required=True)
    plan_resume.add_argument("--case-id", required=True)
    plan_resume.add_argument("--artifact-digest", required=True)
    plan_resume.add_argument("--model-id", required=True)
    plan_resume.add_argument("--suite-fingerprint", required=True)
    plan_resume.add_argument("--runner-version", required=True)
    plan_resume.add_argument("--plan-hash", required=True)

    publish = sub.add_parser("publish", help="Publication bundle helpers.")
    publish_sub = publish.add_subparsers(dest="publish_command", required=True)
    publish_export = publish_sub.add_parser(
        "export",
        help="Export deterministic publication bundle files.",
    )
    publish_export.add_argument(
        "--kind",
        choices=["official-proof", "battlefield-sample", "uploaded-replay"],
        required=True,
    )
    publish_export.add_argument("--plan", type=Path)
    publish_export.add_argument("--artifacts", type=Path)
    publish_export.add_argument("--artifact", type=Path)
    publish_export.add_argument("--out", type=Path, required=True)
    publish_validate = publish_sub.add_parser(
        "validate",
        help="Validate a deterministic publication bundle.",
    )
    publish_validate.add_argument("bundle", type=Path)
    publish_validate.add_argument("--json", action="store_true")

    official = sub.add_parser("official", help="Official result helpers.")
    official_sub = official.add_subparsers(dest="official_command", required=True)
    official_merge = official_sub.add_parser("merge", help="Merge official result artifacts.")
    official_merge.add_argument("run_dir", type=Path)
    official_merge.add_argument("--out", type=Path, required=True)

    providers = sub.add_parser("providers", help="Provider runtime helper commands.")
    providers_sub = providers.add_subparsers(dest="providers_command", required=True)
    providers_preflight = providers_sub.add_parser("preflight", help="Preflight a provider model.")
    providers_preflight.add_argument("--provider", required=True)
    providers_preflight.add_argument("--model", required=True)
    providers_preflight.add_argument("--arena", default="tic-tac-toe", choices=registry.list())

    runner_cmd = sub.add_parser("runner", help="Runner/container helper commands.")
    runner_sub = runner_cmd.add_subparsers(dest="runner_command", required=True)
    runner_health = runner_sub.add_parser("health", help="Print runner health metadata.")
    runner_health.add_argument("--json", action="store_true")
    runner_result = runner_sub.add_parser(
        "result",
        help="Emit a canonical RunnerJobResult from an artifact.",
    )
    runner_result.add_argument("--artifact", type=Path, required=True)
    runner_result.add_argument("--artifact-uri", required=True)
    runner_result.add_argument("--job-id", required=True)

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
    run.add_argument("--runner-version", default="eslams-runner:0.3.0")
    run.add_argument("--suite-id")
    run.add_argument("--case-id")
    run.add_argument("--suite-fingerprint")
    run.add_argument("--plan-hash")
    run.add_argument("--shard-index", type=int)
    run.add_argument("--shard-count", type=int)
    run.add_argument("--runner-result-json", action="store_true")
    run.add_argument("--artifact-uri")

    validate = sub.add_parser("validate", help="Validate an artifact directory or .eslams zip.")
    validate.add_argument("artifact", type=Path)
    validate.add_argument(
        "--profile",
        choices=[
            "runner-bundle",
            "official-bundle",
            "battlefield-bundle",
            "public-replay-package",
            "auto",
        ],
        default="runner-bundle",
    )
    validate.add_argument("--summary-json", action="store_true")

    replay = sub.add_parser("replay", help="Render a local HTML replay from an artifact.")
    replay.add_argument("artifact")
    replay.add_argument("extra", nargs="?")
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
    if args.command == "arena":
        return _arena_command(args)
    if args.command == "schemas":
        return _schemas_command(args)
    if args.command == "artifact":
        return _artifact_command(args)
    if args.command == "fixtures":
        return _fixtures_command(args)
    if args.command == "catalogue":
        return _catalogue_command(args)
    if args.command == "plan":
        return _plan_command(args)
    if args.command == "publish":
        return _publish_command(args)
    if args.command == "official":
        return _official_command(args)
    if args.command == "providers":
        return _providers_command(args)
    if args.command == "runner":
        return _runner_command(args)
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
                suite_id=args.suite_id,
                case_id=args.case_id,
                suite_fingerprint=args.suite_fingerprint,
                plan_hash=args.plan_hash,
                shard_index=args.shard_index,
                shard_count=args.shard_count,
            )
        )
        if args.runner_result_json:
            job_result = runner_job_result_from_artifact(
                artifact_path=result.artifact_path,
                artifact_uri=args.artifact_uri or str(result.artifact_path),
                job_id=result.run_id,
            )
            print(json.dumps(job_result.to_dict(), indent=2))
            return 0 if job_result.validation_status == "valid" else 1
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
        report = ArtifactValidator().validate_report(args.artifact, profile=args.profile)
        payload = report.to_dict()
        if args.summary_json:
            print(json.dumps(payload, sort_keys=True))
            return 0 if report.valid else 1
        if report.errors:
            print(json.dumps(payload, indent=2))
            return 1
        print(json.dumps(payload, indent=2))
        return 0
    if args.command == "replay":
        if args.artifact == "validate-public":
            if args.extra is None:
                print("replay validate-public requires an artifact or directory", file=sys.stderr)
                return 2
            payload = validate_public_replay(Path(args.extra))
            print(json.dumps(payload, indent=2))
            return 0 if payload.get("valid") is True else 1
        output = render_replay_html(Path(args.artifact), args.output)
        print(json.dumps({"replay": str(output)}, indent=2))
        return 0
    if args.command == "agent":
        return _agent_command(args)
    raise AssertionError(args.command)


def _schemas_command(args: argparse.Namespace) -> int:
    if args.schemas_command == "export":
        written = export_schemas(args.out)
        print(json.dumps({"schemas": [str(path) for path in written]}, indent=2))
        return 0
    raise AssertionError(args.schemas_command)


def _arena_command(args: argparse.Namespace) -> int:
    if args.arena_command == "smoke":
        if not args.all_arenas:
            print("arena smoke currently requires --all", file=sys.stderr)
            return 2
        payload = smoke_all_arenas()
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(
                f"ok={str(payload['ok']).lower()} "
                f"game_count={payload['game_count']}"
            )
        return 0 if payload["ok"] is True else 1
    if args.arena_command == "start":
        payload = start_session(
            game_slug=args.game,
            variant=args.variant,
            seed=args.seed,
            players=_json_arg(args.players_json, "players-json"),
            options=_json_arg(args.options_json, "options-json"),
        )
        print(json.dumps(payload, indent=2))
        return 0
    if args.arena_command == "step":
        payload = step_session(
            session_state=_read_json_file(args.state),
            player_id=args.player_id,
            action_token=args.action_token,
        )
        print(json.dumps(payload, indent=2))
        return 0 if payload.get("accepted") is True else 1
    if args.arena_command == "legal-actions-page":
        payload = legal_actions_page(
            session_state=_read_json_file(args.state),
            player_id=args.player_id,
            query=args.query,
            limit=args.limit,
            cursor=args.cursor,
        )
        print(json.dumps(payload, indent=2))
        return 0
    raise AssertionError(args.arena_command)


def _artifact_command(args: argparse.Namespace) -> int:
    if args.artifact_command == "public-export":
        output = export_public_replay(args.artifact, args.out)
        print(json.dumps({"public_replay_package": str(output)}, indent=2))
        return 0
    raise AssertionError(args.artifact_command)


def _fixtures_command(args: argparse.Namespace) -> int:
    if args.fixtures_command == "replay" and args.kind == "uploaded-smoke":
        output = create_uploaded_smoke_fixture(args.out)
        print(json.dumps({"fixture": str(output)}, indent=2))
        return 0
    if args.fixtures_command == "artifact":
        output = create_artifact_fixture(args.kind, args.out)
        print(json.dumps({"fixture": str(output)}, indent=2))
        return 0
    raise AssertionError(args.fixtures_command)


def _catalogue_command(args: argparse.Namespace) -> int:
    rows_by_command: dict[str, Callable[[], list[dict[str, Any]]]] = {
        "games": game_catalogue_rows,
        "models": model_catalogue_rows,
        "availability": availability_rows,
        "renderers": renderer_vocabulary_rows,
    }
    rows = rows_by_command[args.catalogue_command]()
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    for row in rows:
        label = row.get("game_id") or f"{row.get('provider')}:{row.get('model')}"
        print(f"{label} status={row.get('launch_status') or row.get('status') or 'ready'}")
    return 0


def _plan_command(args: argparse.Namespace) -> int:
    if args.plan_command == "official":
        payload = official_plan(
            suite=args.suite,
            providers=_comma_list(args.providers),
            arenas=_comma_list(args.arenas),
            shard_count=args.shard_count,
        )
    elif args.plan_command == "battlefield":
        payload = battlefield_plan(
            pairs=_comma_list(args.pairs),
            arenas=_comma_list(args.arenas),
            shard_count=args.shard_count,
        )
    elif args.plan_command == "public-match":
        payload = public_match_plan(request_path=args.request, shard_count=args.shard_count)
    elif args.plan_command == "progress":
        plan_payload = _read_json_file(args.plan)
        payload = progress_event(
            plan=plan_payload,
            current_case=args.current_case,
            completed_cases=args.completed_cases,
            failed_cases=args.failed_cases,
            skipped_cases=args.skipped_cases,
            elapsed_seconds=args.elapsed_seconds,
            provider_latencies_ms=_int_list(args.provider_latencies_ms),
        )
        append_progress_event(args.out, payload)
    elif args.plan_command == "resume-check":
        invariant = ResumeInvariant(
            case_id=args.case_id,
            artifact_digest=args.artifact_digest,
            model_id=args.model_id,
            suite_fingerprint=args.suite_fingerprint,
            runner_version=args.runner_version,
            plan_hash=args.plan_hash,
        )
        payload = {
            "case_id": args.case_id,
            "skip": should_skip_case(load_resume_checkpoint(args.checkpoint), invariant),
            "resume_key": invariant.resume_key,
        }
    else:
        raise AssertionError(args.plan_command)
    print(json.dumps(payload, indent=2))
    return 0


def _publish_command(args: argparse.Namespace) -> int:
    if args.publish_command == "export":
        output = export_publication_bundle(
            kind=args.kind,
            output_dir=args.out,
            artifacts_dir=args.artifacts,
            artifact=args.artifact,
            plan_path=args.plan,
        )
        print(json.dumps({"publication_bundle": str(output)}, indent=2))
        return 0
    if args.publish_command == "validate":
        payload = validate_publication_bundle(args.bundle)
        if args.json:
            print(json.dumps(payload, indent=2))
        elif payload["valid"]:
            print("publication bundle valid")
        else:
            print("publication bundle invalid")
            for error in payload["errors"]:
                print(f"- {error}")
        return 0 if payload["valid"] is True else 1
    raise AssertionError(args.publish_command)


def _official_command(args: argparse.Namespace) -> int:
    if args.official_command == "merge":
        output = merge_official_results(args.run_dir, args.out)
        print(json.dumps({"official_result": str(output)}, indent=2))
        return 0
    raise AssertionError(args.official_command)


def _providers_command(args: argparse.Namespace) -> int:
    if args.providers_command == "preflight":
        payload = provider_preflight(args.provider, args.model, args.arena)
        print(json.dumps(payload, indent=2))
        return 0 if payload["ok"] is True else 1
    raise AssertionError(args.providers_command)


def _runner_command(args: argparse.Namespace) -> int:
    if args.runner_command == "health":
        payload = current_runner_health()
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(
                f"core_version={payload['core_version']} "
                f"game_count={payload['game_count']}"
            )
        return 0
    if args.runner_command == "result":
        result = runner_job_result_from_artifact(
            artifact_path=args.artifact,
            artifact_uri=args.artifact_uri,
            job_id=args.job_id,
        )
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.validation_status == "valid" else 1
    raise AssertionError(args.runner_command)


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


def _comma_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _int_list(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def _read_json_file(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _json_arg(value: str, name: str) -> dict[str, Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError(f"--{name} must be a JSON object")
    return parsed


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
