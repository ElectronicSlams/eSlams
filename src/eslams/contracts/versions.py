"""Stable schema version names for eSlams Core contracts."""

from __future__ import annotations

ARTIFACT_MANIFEST_SCHEMA_VERSION = "eslams.artifact.manifest.v1"
ARTIFACT_VALIDATION_SCHEMA_VERSION = "eslams.artifact.validation.v1"
REPLAY_PUBLIC_SCHEMA_VERSION = "eslams.replay.public.v1"
REPLAY_MANIFEST_SCHEMA_VERSION = "eslams.replay.manifest.v1"
PROVIDER_RECEIPT_SCHEMA_VERSION = "eslams.provider.receipt.v1"
EVAL_PLAN_SCHEMA_VERSION = "eslams.eval.plan.v1"
EVAL_PROGRESS_SCHEMA_VERSION = "eslams.eval.progress.v1"
EVAL_RESUME_CHECKPOINT_SCHEMA_VERSION = "eslams.eval.resume_checkpoint.v1"
OFFICIAL_RESULT_SCHEMA_VERSION = "eslams.official.result.v1"
PUBLICATION_BUNDLE_SCHEMA_VERSION = "eslams.publication.bundle.v1"
PUBLICATION_VALIDATION_SCHEMA_VERSION = "eslams.publication.validation.v1"
RUNNER_JOB_SCHEMA_VERSION = "eslams.runner.job.v1"
CATALOGUE_GAME_SCHEMA_VERSION = "eslams.catalogue.game.v1"
CATALOGUE_MODEL_SCHEMA_VERSION = "eslams.catalogue.model.v1"

SCHEMA_VERSIONS: tuple[str, ...] = (
    ARTIFACT_MANIFEST_SCHEMA_VERSION,
    ARTIFACT_VALIDATION_SCHEMA_VERSION,
    REPLAY_PUBLIC_SCHEMA_VERSION,
    REPLAY_MANIFEST_SCHEMA_VERSION,
    PROVIDER_RECEIPT_SCHEMA_VERSION,
    EVAL_PLAN_SCHEMA_VERSION,
    EVAL_PROGRESS_SCHEMA_VERSION,
    EVAL_RESUME_CHECKPOINT_SCHEMA_VERSION,
    OFFICIAL_RESULT_SCHEMA_VERSION,
    PUBLICATION_BUNDLE_SCHEMA_VERSION,
    PUBLICATION_VALIDATION_SCHEMA_VERSION,
    RUNNER_JOB_SCHEMA_VERSION,
    CATALOGUE_GAME_SCHEMA_VERSION,
    CATALOGUE_MODEL_SCHEMA_VERSION,
)


def schema_versions() -> tuple[str, ...]:
    """Return all public contract schema versions in deterministic order."""

    return SCHEMA_VERSIONS
