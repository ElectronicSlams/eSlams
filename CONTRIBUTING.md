# Contributing

Thank you for helping build eSlams Core.

## Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check .
mypy src
```

## Design Rules

- Keep public contracts versioned.
- Keep arena identity owned by eSlams, even when logic is adapter-backed.
- Never put hidden official eval content in the public repo.
- Preserve trace privacy boundaries at generation time, not only in UI.
- Add deterministic tests for every arena and artifact behavior.

## Pull Requests

Include:

- a clear behavior summary
- tests for new contracts or arena behavior
- docs for protocol, artifact, or CLI changes
- migration notes when public formats change
