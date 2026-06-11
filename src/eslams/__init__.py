"""Public eSlams framework.

eSlams Core gives agent builders a small, strict contract:

* implement POST /act or use a local Python agent
* run against an eSlams arena
* produce a deterministic trace, replay, score, and artifact
"""

from eslams.agents import MockProviderAgent
from eslams.artifacts import (
    ArtifactManifest,
    ArtifactValidationReport,
    ArtifactValidator,
    SignatureValidationStatus,
    extract_provider_usage,
    extract_public_manifest,
    extract_validation_summary,
    open_artifact,
    read_member,
    write_artifact,
)
from eslams.contracts import schema_versions
from eslams.core_contract import core_step, engine_capabilities, prompt_package
from eslams.protocol import ActRequest, ActResponse
from eslams.runner import RunConfig, Runner
from eslams.state import ArenaState

__all__ = [
    "ActRequest",
    "ActResponse",
    "ArenaState",
    "ArtifactManifest",
    "ArtifactValidationReport",
    "ArtifactValidator",
    "MockProviderAgent",
    "RunConfig",
    "Runner",
    "SignatureValidationStatus",
    "core_step",
    "engine_capabilities",
    "extract_provider_usage",
    "extract_public_manifest",
    "extract_validation_summary",
    "open_artifact",
    "prompt_package",
    "read_member",
    "schema_versions",
    "write_artifact",
]

__version__ = "0.4.0"
