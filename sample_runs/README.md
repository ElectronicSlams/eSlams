# Sample runs

These are keyless Local fixtures for inspection and integration. They establish
no Official or Grand Slam trust and are not provider model evaluation results.
The [inventory](samples.json) records exact checksums and producer commits.

| Sample | Contents | Expected current validation |
| --- | --- | --- |
| [Built-in chess](model_battle_sample/README.md) | Completed first-legal vs first-legal run and `battlefield-sample` publication shape | Runner bundle and publication pass |
| [Local eval shape](model_eval_sample/README.md) | Unsigned tic-tac-toe fixture and `official-proof` publication shape | Runner bundle and publication pass; Official profile fails because unsigned |

They are generated using `scripts/generate_sample_fixtures.py --out <new-directory>`.
No provider key is needed. Fixed fixture creation time is test metadata; measured
timing sidecars are diagnostics. Keep raw archives in private custody; only
allowlisted public exports are public replay inputs. See
[classification](../docs/SAMPLE_CLASSIFICATION.md) and
[custody](../docs/PUBLIC_CUSTODY.md).
