# Contributing

Thank you for helping build eSlams Core.

## Development

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check src tests scripts
python -m mypy src/eslams
tsc -p packages/core-contracts/tsconfig.json
```

Python 3.9, 3.10, 3.11, and 3.12 are supported. Before a release, run the
suite in each interpreter, build the wheel and sdist, run `twine check`, export
the schema bundle twice, and compare the bytes.

## Design Rules

- Keep public contracts versioned.
- Keep arena identity owned by eSlams, even when logic is adapter-backed.
- Never put hidden official eval content in the public repo.
- Preserve trace privacy boundaries at generation time, not only in UI.
- Add deterministic tests for every arena and artifact behavior.
- Treat every provider request as a physical attempt with a stable logical
  action ID, positive gap-free attempt index, explicit attempt kind, and a
  sanitized receipt.
- Never convert provider errors, parse failures, illegal actions, or fallback
  actions into scoring-valid output.
- Never synthesize a resolved provider model from the requested model. Preserve
  unknown identity as `null`; a provider response or explicitly pinned endpoint
  must attest it.

## Provider Fixture Policy

Provider adapter tests use documented raw REST response shapes. SDK convenience
properties are not wire fixtures. In particular, OpenAI Responses fixtures must
contain typed `output[]` items and `output_text` content parts; a top-level SDK
`output_text` field must be rejected by the REST adapter.

For every new or changed provider adapter, include:

- a redacted success fixture copied from the documented wire envelope;
- 400, 401, 403, 404, 429, 5xx, timeout, malformed-body, and missing-usage
  cases;
- request/payload assertions for endpoint and provider-specific controls;
- identity, usage, reasoning-inclusion, and cost assertions;
- a check that credentials, headers, prompts, and raw private responses never
  enter public contracts.

Fixtures live under `tests/fixtures/provider/`. Synthetic payloads are fine for
fault injection, but they must preserve the provider's real envelope.

## Contract Changes

Public contract changes require coordinated updates to the Python dataclass or
serializer, JSON Schema, no-secret example, generated TypeScript type,
documentation, and compatibility tests. New writers emit only the current
version. Readers should retain explicitly tested historical compatibility when
that does not weaken current official validation.

Run `eslams schemas export --out <empty-directory>` and inspect
`schema_bundle_manifest.json` before opening the pull request. Do not hand-edit
an exported schema or deterministic build ID.

## Pull Requests

Include:

- a clear behavior summary
- tests for new contracts or arena behavior
- docs for protocol, artifact, or CLI changes
- changelog entries for user-visible contracts, fixtures, or CLI changes
- migration notes when public formats change
- raw-wire fixture provenance when provider behavior changes
- validation evidence for Python, Ruff, mypy, TypeScript, build, and schema
  determinism when release-facing code changes
