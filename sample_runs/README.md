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
- `model_battle_sample/` uses `run_eeab67d58b994ca7.eslams`, a short built-in
  first-legal versus first-legal chess run (see that directory's README).

Scratch harness state and exploratory local runs are intentionally omitted.
