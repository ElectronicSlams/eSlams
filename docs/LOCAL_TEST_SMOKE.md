# Local test and smoke

How to run Core's local unit tests and the documented keyless smoke commands on a laptop. The check uses this public checkout only. Held infrastructure stays untouched.

**Local green tests ≠ Official ≠ Grand Slam.**

A passing local suite is a developer check. Official and Grand Slam are separate labels. The README verification posture is the boundary: Core creates Local Artifact proof packages, and Official, platform, container, and Grand Slam verification levels come only from controlled eSlams infrastructure.

## Package pin

When you use the published package, develop against the PyPI release:

```bash
pip install eslams-core==0.6.1
```

That pin is the engine you import. The unit suite is the `tests/` tree in this repository. A wheel install does not include it.

This checkout has no `AGENTS.md`. For the monorepo, use the pytest entrypoints already written in the README, `CONTRIBUTING.md`, and `pyproject.toml`.

README Local Development, after the editable dev install:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest
```

`CONTRIBUTING.md` records the same install and the module form:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```

`pyproject.toml` already sets `testpaths = ["tests"]` and `addopts = "-q"`, so `pytest` runs `tests/` quietly. The README release sections also record `python3 -m pytest -q`. Those three invocations are the documented entrypoints. Do not add selectors, markers, or paths that those files do not list.

## Default unit suite

The default unit suite is that pytest run. It does not require R2, D1, Hugging Face, or network secrets. Provider tests use in-repo fixtures and mocked HTTP. `docs/PLATFORM_CONTRACTS.md` states that CI needs no provider API keys and no Cloudflare account. Leave Cloudflare, Hugging Face, and provider credentials unset for this suite.

Live preflight (`eslams providers preflight ... --live`) and `eslams models update` are separate README commands. They call provider networks and sit outside the default unit suite.

## Documented local smoke

These commands are already in the README and `docs/ARENAS.md`. They are local CLI checks on built-in agents and the in-tree registry. They remain Local Artifact work: local green smoke ≠ Official ≠ Grand Slam.

README Local Development:

```bash
eslams run --arena chess --agent first-legal --opponent first-legal --max-turns 8
eslams validate runs/latest.eslams
eslams replay runs/latest.eslams
eslams models list --provider openai --game-agent-supported
```

README and `docs/ARENAS.md`:

```bash
eslams arena smoke --all --json
```

`.github/workflows/ci.yml` runs `pytest`, then these two smoke steps. Bind and CI hygiene already live on #26. This page does not change that workflow.

```bash
eslams schemas export --out /tmp/eslams-schemas
python -m eslams_core.bench arena-step --games tic-tac-toe --iterations 10 --json /tmp/core-step-bench.json
```

The README v0.4.0 section records the same bench entry as `python3 -m eslams_core.bench arena-step --games tic-tac-toe --iterations 10 --json out/core-step-bench.json`.

## Related drafts

Pointers by number only. This page does not restate or replace them.

- #18 — lab-smoke and `LAB_RUN`
- #24 — Wave A lab path
- #25 — contributor holds
- #26 — F7–F10 (replay trust, sample agent bind, CI hygiene). That draft already implements bind and CI hygiene. Do not re-code it here.
- #27 — public vs private Core surface

## Agent holds

No merge, no deploy, no DNS change, no R2 pull, no D1 delete, and no Hugging Face upload. Running the local suite is the whole task.
