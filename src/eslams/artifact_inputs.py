"""Select validated, distinct artifacts for aggregate exports."""

from pathlib import Path

from eslams.artifacts import ArtifactValidator


def artifact_inputs(*, directory: Path | None = None, artifact: Path | None = None) -> list[Path]:
    if (directory is None) == (artifact is None):
        raise ValueError("provide exactly one artifact or artifact directory")
    if artifact is not None:
        candidates = [artifact]
    else:
        assert directory is not None
        if not directory.is_dir():
            raise ValueError("artifact directory does not exist or is not a directory")
        candidates = [
            path
            for path in sorted(directory.iterdir())
            if path.name.endswith((".eslams", ".eslams.d"))
            and not path.name.startswith("latest.eslams")
            and not (path.name.endswith(".eslams.d") and path.with_suffix("").is_file())
        ]
    selected: dict[str, Path] = {}
    for path in candidates:
        report = ArtifactValidator().validate_report(path, profile="auto")
        if not report.valid or not report.artifact_id:
            details = "; ".join(report.errors) or "missing artifact identity"
            raise ValueError(f"invalid artifact {path.name}: {details}")
        selected.setdefault(report.artifact_id, path.resolve())
    if not selected:
        raise ValueError(
            "no artifacts found; aggregate output requires at least one valid artifact"
        )
    return [selected[key] for key in sorted(selected)]
