# lab-smoke

Keyless local smoke for eSlams Core **0.6.1**.

**Local Artifact ≠ Official / Grand Slam.**

These cases use builtin `random` and `first-legal` agents, `--execution-profile smoke`, and `--verification-level "Local Artifact"`. They do not call provider APIs, do not use eSlams org keys, and do not produce Official or Grand Slam scores. They are not a public leaderboard. The Platform leaderboard product is retired / retiring.

## What is in the suite

10 cases across four arenas:

| Arena | Cases |
| --- | --- |
| `tic-tac-toe` | 3 |
| `connect-four` | 3 |
| `othello` | 2 |
| `chess` | 2 (capped with `--max-turns 8`) |

Case files live in `cases/`. `manifest.yaml` pins `eslams-core` / `core_pin: "0.6.1"`.

## Run

From a checkout of this repo, with the pinned package installed:

```bash
pip install eslams-core==0.6.1
python suites/lab-smoke/run_keyless.py
```

Preview the CLI without writing artifacts:

```bash
python suites/lab-smoke/run_keyless.py --dry-run
```

Artifacts land in `runs/lab-smoke/` (gitignored). The runner validates each archive with `eslams validate --profile runner-bundle` and checks that the manifest says `Local Artifact` and `execution_profile: smoke`.

The runner rejects any case whose agent is not `random` or `first-legal`, so this path cannot spend a provider key.

## Keyed smoke is separate

A single BYO model smoke is documented in [docs/LABS.md](../../docs/LABS.md). Export **your** key, then run one `eslams run … --execution-profile smoke` command. Do not put that key in this suite, in CI, or in an org secret store for lab runs.

## Related docs

- [docs/LABS.md](../../docs/LABS.md)
- [docs/PROVIDERS.md](../../docs/PROVIDERS.md)
- [SECURITY.md](../../SECURITY.md)
