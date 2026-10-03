"""Deterministic fixture generation helpers."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from eslams.output import staged_file
from eslams.runner import RunConfig, Runner

ARTIFACT_FIXTURE_KINDS: tuple[str, ...] = (
    "local-tic-tac-toe",
    "official-unsigned",
    "official-signed",
)


def create_artifact_fixture(kind: str, output_path: Path, *, overwrite: bool = False) -> Path:
    if kind not in ARTIFACT_FIXTURE_KINDS:
        valid = ", ".join(ARTIFACT_FIXTURE_KINDS)
        raise ValueError(f"artifact fixture kind must be one of: {valid}")
    # Runner owns every output and latest pointer under this private root.
    # The filename is independent of the portable internal run id.
    with staged_file(output_path, overwrite=overwrite) as staged, \
            tempfile.TemporaryDirectory(prefix="eslams-fixture-") as temporary:
        run_id = "fixture_" + kind.replace("-", "_")
        config = RunConfig(
            arena_id="tic-tac-toe",
            agent_1="first-legal",
            agent_2="first-legal",
            seed=1,
            max_turns=5,
            run_id=run_id,
            output_dir=Path(temporary),
            archive=True,
            verification_level="Official Fixture" if kind.startswith("official")
            else "Local Fixture",
            eval_suite_version="official-fixture:1.0.0" if kind.startswith("official")
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
        shutil.copyfile(artifact, staged)
    return output_path.resolve()


@contextmanager
def _temporary_signing_env() -> Iterator[None]:
    previous_key = os.environ.get("RUNNER_ARTIFACT_SIGNING_PRIVATE_KEY")
    previous_key_id = os.environ.get("RUNNER_ARTIFACT_SIGNING_KEY_ID")
    os.environ["RUNNER_ARTIFACT_SIGNING_PRIVATE_KEY"] = (
        "base64:MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
    )
    os.environ["RUNNER_ARTIFACT_SIGNING_KEY_ID"] = "fixture-key"
    try:
        yield
    finally:
        _restore_env("RUNNER_ARTIFACT_SIGNING_PRIVATE_KEY", previous_key)
        _restore_env("RUNNER_ARTIFACT_SIGNING_KEY_ID", previous_key_id)


@contextmanager
def _without_signing_env() -> Iterator[None]:
    previous_key = os.environ.get("RUNNER_ARTIFACT_SIGNING_PRIVATE_KEY")
    previous_key_id = os.environ.get("RUNNER_ARTIFACT_SIGNING_KEY_ID")
    os.environ.pop("RUNNER_ARTIFACT_SIGNING_PRIVATE_KEY", None)
    os.environ.pop("RUNNER_ARTIFACT_SIGNING_KEY_ID", None)
    try:
        yield
    finally:
        _restore_env("RUNNER_ARTIFACT_SIGNING_PRIVATE_KEY", previous_key)
        _restore_env("RUNNER_ARTIFACT_SIGNING_KEY_ID", previous_key_id)


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value

