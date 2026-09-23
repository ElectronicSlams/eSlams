# Docs index

Table of contents for lab and OSS documentation in this repository.
Checked **2026-09-23**.

[On `main`](#on-main) lists files that are already on the default branch. Every other lab page in [By purpose](#by-purpose) names the pull request that contains it. A **draft #N** file is in that draft and is absent from `main`.

**Local Artifact ≠ Official ≠ Grand Slam.**

A local run, a green `pytest`, or `pip install eslams-core==0.6.1` produces a Local Artifact. Official and Grand Slam come only from controlled eSlams infrastructure. That boundary is already on `main` in [Verification Posture](../README.md#verification-posture). Claim wording for lab users is draft [#32](https://github.com/ElectronicSlams/eSlams/pull/32).

Platform is a different repository. This page does not document Core Platform F3 or Workers deploy steps.

## Holds

From this OSS repository:

- No merge, no deploy, and no DNS change.
- No R2 pull, no D1 query or delete, and no Hugging Face org, dataset, Collection, or Space create or upload. Do not invent a Hub URL.
- Leave the bodies of [#19](https://github.com/ElectronicSlams/eSlams/pull/19), [#20](https://github.com/ElectronicSlams/eSlams/pull/20), and [#21](https://github.com/ElectronicSlams/eSlams/pull/21) alone.

This page is a table of contents. It is not a merge list.

## On `main`

| Path | Purpose |
| --- | --- |
| [README.md](../README.md) | Install, quick start, and verification posture |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Dev install and the documented pytest entrypoints |
| [SECURITY.md](../SECURITY.md) | Vulnerability reports and secret boundaries |
| [CHANGELOG.md](../CHANGELOG.md) | Release notes through Core 0.6.1 |
| [docs/ARENAS.md](ARENAS.md) | Arena catalogue and public smoke arenas |
| [docs/PROTOCOL.md](PROTOCOL.md) | `POST /act` protocol |
| [docs/PROVIDERS.md](PROVIDERS.md) | Provider wire adapters and credential env vars |
| [docs/ARTIFACTS.md](ARTIFACTS.md) | `.eslams` proof packages and validation profiles |
| [docs/PLATFORM_CONTRACTS.md](PLATFORM_CONTRACTS.md) | Portable contracts Core emits; Core does not upload to R2 or write D1 |
| [docs/REGISTRY_AVAILABLE_MODELS.md](REGISTRY_AVAILABLE_MODELS.md) | Source-backed model catalog snapshot, not an availability claim |
| [sample_runs/README.md](../sample_runs/README.md) | In-repo sample index as committed on `main` |

The published package pin in `pyproject.toml` is `eslams-core==0.6.1`.

## By purpose

### Getting started / Wave A lab path

- On `main`: [Install](../README.md#install) and [Quick Start](../README.md#quick-start).
- `docs/LABS.md` is the BYO-key lab quickstart. It is open pull request [#13](https://github.com/ElectronicSlams/eSlams/pull/13). That pull request is not a draft, and the file is not on `main`.
- `docs/WAVE_A_LAB_PATH.md` is the Wave A index that points at `docs/LABS.md`. Draft [#24](https://github.com/ElectronicSlams/eSlams/pull/24).

### Local test and smoke

- On `main`: [CONTRIBUTING.md](../CONTRIBUTING.md) (`python -m pytest -q` after `pip install -e ".[dev]"`) and the local CLI checks in the README.
- `docs/LOCAL_TEST_SMOKE.md` collects those entrypoints and states that a green local suite stays a Local Artifact. Draft [#29](https://github.com/ElectronicSlams/eSlams/pull/29).

### PyPI consumer

- On `main`: [Install](../README.md#install) (`pip install eslams-core`) and `pyproject.toml` version `0.6.1`.
- `docs/PYPI_CONSUMER.md` is the consumer page for the published `eslams-core==0.6.1` wheel. Draft [#31](https://github.com/ElectronicSlams/eSlams/pull/31).

### Public vs private / claim vocabulary

- On `main`: [Verification Posture](../README.md#verification-posture). **Local Artifact ≠ Official ≠ Grand Slam.**
- `docs/PUBLIC_VS_PRIVATE_SURFACE.md` is the public-versus-held surface index. Draft [#27](https://github.com/ElectronicSlams/eSlams/pull/27).
- `docs/CLAIM_VOCAB.md` is the claim-vocabulary page. Draft [#32](https://github.com/ElectronicSlams/eSlams/pull/32).

### Contributor holds / founder gates

- On `main`: [SECURITY.md](../SECURITY.md).
- `docs/CONTRIBUTOR_HOLDS.md` is contributor and agent hygiene. Draft [#25](https://github.com/ElectronicSlams/eSlams/pull/25).
- `docs/FOUNDER_GATES_AND_OPEN_DRAFTS.md` is the founder-gate status index. Draft [#23](https://github.com/ElectronicSlams/eSlams/pull/23).

### Core Low F7–F10

- Code is draft [#26](https://github.com/ElectronicSlams/eSlams/pull/26) only. Do not open a second implementation.
- Status index `docs/CORE_LOW_F7_F10_STATUS.md` points at [#26](https://github.com/ElectronicSlams/eSlams/pull/26). Draft [#28](https://github.com/ElectronicSlams/eSlams/pull/28).
- On `main`, the protocol page those findings cite is [docs/PROTOCOL.md](PROTOCOL.md). The #26 edits to that page are not on `main`.

### Open drafts map

- `docs/OPEN_OSS_DRAFTS.md` is the reviewer map of open OSS drafts. Draft [#30](https://github.com/ElectronicSlams/eSlams/pull/30).
- This page is the purpose index. Draft #30 is the pull-request map. Draft #23 is the founder-gate index.

### Lab-pack honesty / A-EX

- On `main`: [sample_runs/README.md](../sample_runs/README.md). This index does not add sample run ids.
- `docs/LAB_PACK.md` and `docs/A_EX_PLAN.md` are the in-repo lab-pack honesty note and the A-EX ≤50 teaching-fail plan. Both are draft [#22](https://github.com/ElectronicSlams/eSlams/pull/22).

### Lab smoke / LAB_RUN

- `docs/LAB_RUN.md` and `suites/lab-smoke/` are the keyless lab-smoke path. Draft [#18](https://github.com/ElectronicSlams/eSlams/pull/18).
- That draft complements `docs/LABS.md` in [#13](https://github.com/ElectronicSlams/eSlams/pull/13). Neither file is on `main`.

## How to read a row

A relative link in this file resolves on `main`. A **draft #N** (or open pull request #13) is the place to read that filename until the pull request is on the default branch.
