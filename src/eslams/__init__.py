"""Public eSlams framework.

eSlams Core gives agent builders a small, strict contract:

* implement POST /act or use a local Python agent
* run against an eSlams arena
* produce a deterministic trace, replay, score, and artifact
"""

from eslams.artifacts import (
    ArtifactManifest,
    ArtifactValidationReport,
    ArtifactValidator,
    SignatureValidationStatus,
    write_artifact,
)
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
    "RunConfig",
    "Runner",
    "SignatureValidationStatus",
    "write_artifact",
]

__version__ = "0.1.0"
