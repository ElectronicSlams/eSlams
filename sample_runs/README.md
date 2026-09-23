Sample Runs
===========

This directory contains curated sample run material for stadium ingestion and
developer inspection. These files are thin GitHub samples. They are not a
public leaderboard.

Selection criteria:

- the source artifact validates under its intended profile;
- deterministic replay validation passes;
- the run has no recorded error-log entries;
- model-battle samples must not rely on missing-key fallback actions;
- publication bundles validate with `eslams publish validate`.

Included samples:

- `model_eval_sample/` uses the signed official fixture artifact as a compact
  historical model-eval publication example. It is not a live ranking row.
- `model_battle_sample/` uses `run_d48ff364a0b949df`, a curated chess battle
  between `composer-2.5` and `grok-build-0.1`.

Scratch harness state and exploratory local runs are intentionally omitted.
