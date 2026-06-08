Sample Runs
===========

This directory contains curated sample run material for Platform ingestion and
developer inspection.

Selection criteria:

- the source artifact validates under its intended profile;
- deterministic replay validation passes;
- the run has no recorded error-log entries;
- model-battle samples must not rely on missing-key fallback actions;
- publication bundles validate with `eslams publish validate`.

Included samples:

- `model_eval_sample/` uses the signed official fixture artifact as a compact
  model-eval publication example.
- `model_battle_sample/` uses `run_d48ff364a0b949df`, the clean Cursor harness
  chess battle between `composer-2.5` and `grok-build-0.1`.

Excluded local runs:

- `run_28d155e78bd744ac` validates structurally, but both players used
  missing-key fallback actions.
- `run_e2c6c4618710446d` validates structurally, but both players used
  missing-key fallback actions.
- the active Cursor harness folders are scratch harness state; only
  `cursor-harness-test` completed, producing `run_d48ff364a0b949df`.
