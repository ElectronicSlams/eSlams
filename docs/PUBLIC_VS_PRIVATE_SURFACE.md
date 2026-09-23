# Public vs private surface

Index for lab users. This page says what is public open-source surface today,
and what is held, retired, or a different repository.

It is one link per related draft. It does not rewrite those drafts, pull
archives, delete databases, create a Hub org, deploy, change DNS, or merge.

## Public now

These are the live Core surfaces:

| Surface | What you can use |
| --- | --- |
| This GitHub repository | [ElectronicSlams/eSlams](https://github.com/ElectronicSlams/eSlams): source, in-repo docs, and the sample tree as committed on the default branch. |
| PyPI | `eslams-core==0.6.1`. Labs bring their own provider keys. |
| In-repo samples and docs | Public as files in this repository. Treat the lab pack as the honest path only by following [#22](https://github.com/ElectronicSlams/eSlams/pull/22) (lab-pack honesty) and [#24](https://github.com/ElectronicSlams/eSlams/pull/24) (Wave A lab path). This page does not cite sample run ids. |

```bash
pip install eslams-core==0.6.1
```

## Held, retired, or not live

| Item | Status |
| --- | --- |
| Hugging Face org `ElectronicSlams` | 404 until the founder creates it. This page does not invent a Hub, dataset, Collection, or Space URL, and it does not claim `hf download`. |
| R2 archives | HOLD. No pull from this page. The HOLD runbook is [#20](https://github.com/ElectronicSlams/eSlams/pull/20). |
| D1 deletes | HOLD. No delete from this page. Founder gates stay on [#23](https://github.com/ElectronicSlams/eSlams/pull/23). |
| Official public leaderboard | Retired. The Core retirement text is [#19](https://github.com/ElectronicSlams/eSlams/pull/19). This page does not rewrite that draft. |
| Grand Slam from a local run | A local run does not establish a Grand Slam. |

## Local Artifact, Official, and Grand Slam

These are three separate labels:

- **Local Artifact.** What `eslams run` writes on a machine using Core.
- **Official.** A historical verification level. Retirement of the public leaderboard and the Official suite is [#19](https://github.com/ElectronicSlams/eSlams/pull/19).
- **Grand Slam.** A stadium claim. It is not a label a local Core run confers.

A Local Artifact is a Local Artifact. It is neither Official nor a Grand Slam.

## Platform is a different repository

Hosted product code lives in `makriman/eSlamsPlatform` (or the equivalent Platform repository). Core publishes the evaluation engine and the contract docs in this repository. Core does not ship Cloudflare Workers. Platform deploy steps belong in that repository, not here.

## Related drafts

Read these by number. Each link is an index pointer only.

| PR | Role |
| --- | --- |
| [#23](https://github.com/ElectronicSlams/eSlams/pull/23) | Founder gates and open Core drafts |
| [#24](https://github.com/ElectronicSlams/eSlams/pull/24) | Wave A lab path |
| [#25](https://github.com/ElectronicSlams/eSlams/pull/25) | Contributor holds |
| [#22](https://github.com/ElectronicSlams/eSlams/pull/22) | Lab-pack honesty |
| [#21](https://github.com/ElectronicSlams/eSlams/pull/21) | Runner HTTP authorization (do not implement from this page) |
| [#19](https://github.com/ElectronicSlams/eSlams/pull/19) | Public leaderboard and Official suite retirement |

## Low findings on a separate track

F7–F10 may be in flight on their own drafts. This page does not implement them.

| ID | Topic |
| --- | --- |
| F7 | Replay trust |
| F8 | Agent bind |
| F9 | CI hygiene |
| F10 | PROTOCOL / core-lite |
