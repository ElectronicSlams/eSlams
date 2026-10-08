# Contributing

Thank you for helping build eSlams Core.

## Development

On Linux/macOS, install from a Git clone inside a virtual environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python -m mypy src/eslams
```

On Windows PowerShell:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy src/eslams
```

Install Node.js/npm separately for both TypeScript checks (the Python dev extra
does not install TypeScript). Run these commands from the repository root on
either platform:

```bash
npx --yes --package typescript@5.5.4 tsc --noEmit -p packages/core-contracts/tsconfig.json
npx --yes --package typescript@5.5.4 tsc --noEmit -p packages/core-lite/tsconfig.json
```

Editor whitespace defaults are in `.editorconfig`; Git text checkouts use LF
through `.gitattributes`. This consolidation does not install a pre-commit
formatter or perform repository-wide formatting. Ruff lint is the required
style check. PR #42 is declined because its formatter would mix unrelated
rewrites into ordinary commits and its installation is missing from dev setup.
PR #47's blanket-suppressed Bandit job is also declined; focused service,
artifact and privacy regressions remain required. Dependency and workflow
audits are tracked separately and do not establish runtime safety by themselves.

`.env.example` lists supported names with empty values. Core does not load it
automatically. Export only the settings you intend to configure; exporting
all empty placeholders can override defaults and trigger fail-closed checks.
See `SECURITY.md` for session/request secrets and `docs/ARTIFACTS.md` for signing.
Real `.env` files are ignored.

The proposed dependency baseline requires Python 3.10+; CI checks 3.10, 3.11
and 3.12. Published Core 0.6.1 remains compatible with Python 3.9. Mypy uses the active
interpreter version so installed dependency syntax is checked correctly; CI
checks each supported version explicitly. Run mypy from that interpreter’s
virtual environment. Before a release, run the
suite in each interpreter, build the wheel and sdist, run `twine check`, export
the schema bundle twice, and compare the bytes.

## Contributor shortcuts and checks

On systems with Make, `make help` lists shortcuts for the commands above.
Use `make check PYTHON=.venv/bin/python` after installing the dev extra and
Node.js/npm. Schema and benchmark outputs go to ignored `.checks/`; override
`CHECK_OUTPUT_DIR` to choose a different scratch directory. Windows contributors
can use the direct Python and npm commands without installing Make.

Core CI and isolated distribution consumers already run keyless game, validate,
replay and export checks. `tests/test_contract_artifact_profiles.py` covers Local
Artifact gameplay validity and publication boundaries, so the standalone smoke
proposed in #38 is consolidated into those existing checks.

Dependabot proposes weekly grouped Python and GitHub Actions updates. Updates
require review and the existing native, distribution and audit gates; there is no
automatic merge. SHA-pinned CodeQL scans Python and TypeScript on PRs, main and
a weekly schedule. Its report is one additional source of review evidence.

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

## Community and reports

Follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Bug reports should include
version/commit, OS, Python, exact commands, expected/actual behavior and redacted
output. GitHub issue and PR templates collect this context. Security reports use
[SECURITY.md](SECURITY.md), not public reproduction details containing secrets.

Source contribution does not authorize a deployment, storage extract or data
publication. Keep such operations in a separately scoped task. The canonical
[docs index](docs/DOCS_INDEX.md) and resolution ledger replace the old overlapping
draft maps; proposed draft account/founder policies are not silently adopted.

Run `python scripts/verify_arena_versions.py` and `eslams core budgets --json`
alongside the relevant rules tests. Behavior changes need an arena version bump
and reviewed trajectory fingerprints; see [versioning](docs/ARENA_VERSIONING.md).
The budget command checks initial states, using approximate prompt tokens,
not all future turns or a provider tokenizer.

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

## Dependency baseline

Runtime floors are HTTPX 0.28.1, FastAPI 0.142.4, Starlette 1.7.0,
Uvicorn 0.54.0 and cryptography 50.0.2. The dev extra uses pytest 9.1.1+,
build 1.6.1+, Twine 7+ and setuptools 83+. The setuptools floor upgrades
older bootstrap copies installed in Python 3.10 virtual environments. Build isolation uses Hatchling 1.32.4+, whose
Metadata 2.5 output is understood by Twine 7. These are proposed source
requirements; they do not change an already published wheel.

The [pytest advisory](https://osv.dev/vulnerability/GHSA-6w46-j5rx-g56g) affects
versions through 9.0.2, while [patched pytest](https://pypi.org/project/pytest/9.1.1/)
and [Twine 7](https://pypi.org/project/twine/7.0.0/) require Python 3.10+.
Current [FastAPI](https://pypi.org/project/fastapi/0.142.4/) and
[Starlette](https://pypi.org/project/starlette/1.7.0/) also require 3.10+.
Keep CI's pytest temporary root inside the runner-owned temporary directory.
Dependency audits must run against both current resolution and the declared
direct floors. An audit failure requires a reviewed fix; no blanket advisory
ignore list is accepted in this consolidation.
