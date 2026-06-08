"""Publication bundle and proof-index contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from eslams.contracts.versions import (
    PUBLICATION_BUNDLE_SCHEMA_VERSION,
    PUBLICATION_VALIDATION_SCHEMA_VERSION,
)


@dataclass(frozen=True)
class ObjectManifestEntry:
    path: str
    sha256: str
    bytes: int
    content_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "content_type": self.content_type,
        }


@dataclass(frozen=True)
class PublicationBundleManifest:
    kind: str
    plan_hash: str | None
    object_manifest_hash: str
    completed_object_count: int
    completed_projection_chunk_count: int
    objects: list[ObjectManifestEntry] = field(default_factory=list)
    schema_version: str = PUBLICATION_BUNDLE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "plan_hash": self.plan_hash,
            "object_manifest_hash": self.object_manifest_hash,
            "completed_object_count": self.completed_object_count,
            "completed_projection_chunk_count": self.completed_projection_chunk_count,
            "objects": [item.to_dict() for item in self.objects],
        }


def no_secret_examples() -> dict[str, dict[str, Any]]:
    bundle = PublicationBundleManifest(
        kind="battlefield-sample",
        plan_hash="plan_hash_example",
        object_manifest_hash="object_manifest_hash_example",
        completed_object_count=1,
        completed_projection_chunk_count=4,
        objects=[ObjectManifestEntry(path="proof_index.jsonl", sha256="sha256_example", bytes=42)],
    ).to_dict()
    validation = {
        "schema_version": PUBLICATION_VALIDATION_SCHEMA_VERSION,
        "bundle_dir": "fixtures/publication/battlefield_sample_bundle",
        "kind": "battlefield-sample",
        "valid": True,
        "status": "valid",
        "object_count": 1,
        "projection_chunk_count": 4,
        "object_manifest_hash": "object_manifest_hash_example",
        "statement_projection_hash": "statement_projection_hash_example",
        "errors": [],
    }
    return {
        PUBLICATION_BUNDLE_SCHEMA_VERSION: bundle,
        PUBLICATION_VALIDATION_SCHEMA_VERSION: validation,
    }
