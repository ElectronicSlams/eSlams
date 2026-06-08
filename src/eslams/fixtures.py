"""Deterministic fixture generation helpers."""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from eslams.runner import RunConfig, Runner

ARTIFACT_FIXTURE_KINDS: tuple[str, ...] = (
    "local-tic-tac-toe",
    "official-unsigned",
    "official-signed",
)


def create_artifact_fixture(kind: str, output_path: Path) -> Path:
    if kind not in ARTIFACT_FIXTURE_KINDS:
        valid = ", ".join(ARTIFACT_FIXTURE_KINDS)
        raise ValueError(f"artifact fixture kind must be one of: {valid}")
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_id = output_path.name.removesuffix(".eslams")
    config = RunConfig(
        arena_id="tic-tac-toe",
        agent_1="first-legal",
        agent_2="first-legal",
        seed=1,
        max_turns=5,
        run_id=run_id,
        output_dir=output_path.parent,
        archive=True,
        verification_level="Official Fixture" if kind.startswith("official") else "Local Fixture",
        eval_suite_version="official-fixture:1.0.0"
        if kind.startswith("official")
        else "fixture-local:1.0.0",
        suite_id="official-fixture" if kind.startswith("official") else "local-fixture",
        case_id=run_id,
        suite_fingerprint="fixture-suite",
        plan_hash="fixture-plan",
    )
    if kind == "official-signed":
        with _temporary_signing_env():
            artifact = Runner().run(config).artifact_path
    else:
        with _without_signing_env():
            artifact = Runner().run(config).artifact_path
    if artifact != output_path and artifact.exists():
        shutil.move(str(artifact), output_path)
    _cleanup_runner_fixture_outputs(output_path)
    return output_path


@contextmanager
def _temporary_signing_env() -> Iterator[None]:
    previous_key = os.environ.get("RUNNER_SIGNING_KEY")
    previous_key_id = os.environ.get("RUNNER_SIGNING_KEY_ID")
    os.environ["RUNNER_SIGNING_KEY"] = "fixture-signing-key"
    os.environ["RUNNER_SIGNING_KEY_ID"] = "fixture-key"
    try:
        yield
    finally:
        _restore_env("RUNNER_SIGNING_KEY", previous_key)
        _restore_env("RUNNER_SIGNING_KEY_ID", previous_key_id)


@contextmanager
def _without_signing_env() -> Iterator[None]:
    previous_key = os.environ.get("RUNNER_SIGNING_KEY")
    previous_key_id = os.environ.get("RUNNER_SIGNING_KEY_ID")
    os.environ.pop("RUNNER_SIGNING_KEY", None)
    os.environ.pop("RUNNER_SIGNING_KEY_ID", None)
    try:
        yield
    finally:
        _restore_env("RUNNER_SIGNING_KEY", previous_key)
        _restore_env("RUNNER_SIGNING_KEY_ID", previous_key_id)


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


def _cleanup_runner_fixture_outputs(output_path: Path) -> None:
    expanded = output_path.with_suffix(".eslams.d")
    if expanded.exists():
        shutil.rmtree(expanded)
    for name in ("latest.eslams", "latest.eslams.d"):
        latest = output_path.parent / name
        if latest.exists() or latest.is_symlink():
            if latest.is_dir() and not latest.is_symlink():
                shutil.rmtree(latest)
            else:
                latest.unlink()
