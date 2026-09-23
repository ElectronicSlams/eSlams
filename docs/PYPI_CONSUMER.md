# Using `eslams-core` 0.6.1 from PyPI

This page is for someone who wants the published Core package for a local or
lab run. Install it from PyPI. You do not need to clone this monorepo, and you
do not need R2, D1, a Hugging Face org, or a Platform deploy.

The pin matches `pyproject.toml` (`version = "0.6.1"`) and the
[Install](../README.md#install) section of the README (`pip install eslams-core`).
The command below pins that published release.

## Install

Core supports Python 3.9 through 3.12 (`Requires-Python: >=3.9`; README and
classifiers stop at 3.12).

```bash
pip install eslams-core==0.6.1
```

PyPI project: <https://pypi.org/project/eslams-core/0.6.1/>

That install uses the wheel `eslams_core-0.6.1-py3-none-any.whl`. The installed
import packages are `eslams` and `eslams_core`. The console script is `eslams`
(`eslams.cli:main`).

This markdown file is not inside that wheel. `eslams-core==0.6.1` was published
before this page existed. Reading this page means you are looking at the git
repository (or a later checkout). It does not mean the 0.6.1 wheel grew new
files.

## What the package is for

`eslams-core` is the public local and lab evaluation engine: run a game, write
a portable `.eslams` archive, validate it, and render a replay. The PyPI
summary is "Public eSlams framework for AI game agents, deterministic runs,
artifacts, and replays."

A keyless local run, copied from the README quick start:

```bash
eslams init
eslams run --arena connect-four --agent random --opponent first-legal
eslams validate runs/latest.eslams
eslams replay runs/latest.eslams
```

`eslams run` writes:

- `runs/<run_id>.eslams`, a portable zip-compatible archive
- `runs/<run_id>.eslams.d`, an expanded inspection directory
- `runs/latest.eslams` and `runs/latest.eslams.d`, pointers to the latest run

List arenas from the installed copy:

```bash
eslams arenas
```

Those commands create a **Local Artifact**. Official leaderboard rows and
Grand Slam verification are produced only by controlled eSlams infrastructure
(secret seeds, private scenario sets, hidden eval variants). A local run from
this package does not create those claims.

Platform Workers are a different system. This package does not ship Workers,
Durable Objects, or a Platform deploy.

Provider-backed model agents are documented in the README
([Run Model Agents](../README.md#run-model-agents)) and in
[docs/PROVIDERS.md](PROVIDERS.md). Keys stay in the environment variables named
there. The `random` / `first-legal` run above does not need them.

## What 0.6.1 does not ship

`pip install eslams-core==0.6.1` does not install `@eslams/core-lite` or
`@eslams/core-contracts`.

Checked against the published 0.6.1 artifacts and this repository:

- The wheel's top-level packages are `eslams` and `eslams_core` only.
- The npm registry returns 404 for `@eslams/core-lite` and
  `@eslams/core-contracts`.
- In this repository, `packages/core-lite/package.json` is still version
  `0.4.0` and depends on `@eslams/core-contracts` `0.4.0`.
  `packages/core-contracts/package.json` is `0.6.1`. The 0.6.1 source
  distribution contains those TypeScript sources; they are not a published
  package, and they are not in the wheel.

[#26](https://github.com/ElectronicSlams/eSlams/pull/26) is the draft that
records core-lite as unpublished until that package metadata is bumped. This
page does not publish it and does not treat core-lite as a feature of
`eslams-core==0.6.1`.

`suites/lab-smoke` is not in the 0.6.1 wheel or source distribution. The
keyless lab suite and `docs/LAB_RUN.md` belong to
[#18](https://github.com/ElectronicSlams/eSlams/pull/18).

## Open drafts, by number

Read these drafts for the surrounding lab and hold context. This page does not
restate or rewrite them, and it does not rewrite #19–#27.

| Draft | What it owns |
| --- | --- |
| [#24](https://github.com/ElectronicSlams/eSlams/pull/24) | Wave A lab path |
| [#18](https://github.com/ElectronicSlams/eSlams/pull/18) | `LAB_RUN` / lab-smoke |
| [#27](https://github.com/ElectronicSlams/eSlams/pull/27) | Public vs private surface |
| [#25](https://github.com/ElectronicSlams/eSlams/pull/25) | Contributor holds |
| [#26](https://github.com/ElectronicSlams/eSlams/pull/26) | F7–F10 (replay trust, sample-agent bind, CI hygiene, protocol and core-lite notes) |

Bind and CI changes for F7–F10 are already in #26. This page does not re-code
them, and the published 0.6.1 wheel does not include them.

## Holds

This page does not authorize any of the following:

- R2 pull or upload
- D1 delete
- Hugging Face org `ElectronicSlams` (404 until the founder). No Hub download,
  org create, or upload from this page. No Hub URL is given here.
- Merge, deploy, or DNS changes

Installing `eslams-core==0.6.1` and running the local commands above is the
whole consumer path this page describes.
