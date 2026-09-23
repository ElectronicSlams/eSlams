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
- `model_battle_sample/` uses `run_eeab67d58b994ca7`, a deterministic chess
  battle between built-in `first-legal` agents.

`model_eval_sample/official_signed.eslams` is a fixture shape, not a live
Official suite. The Official suite is retired / historical. Bulk samples are
planned on the Hugging Face warehouse; see [docs/HF_LAB.md](../docs/HF_LAB.md).
Lab installs pin `eslams-core==0.6.1`.

Scratch harness state and exploratory local runs are intentionally omitted.
