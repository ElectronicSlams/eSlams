Sample Runs
===========

This directory contains curated sample run material for developer inspection.
These files are the in-repo lab pack. They are not a Hugging Face dataset
and they are not a public leaderboard. See [docs/LAB_PACK.md](../docs/LAB_PACK.md).

Selection criteria:

- the source artifact validates under its intended profile;
- deterministic replay validation passes;
- the run has no recorded error-log entries;
- model-battle samples must not rely on missing-key fallback actions;
- publication bundles validate with `eslams publish validate`.

Included samples:

- `model_eval_sample/` uses `official_signed.eslams`, a signed official fixture.
  It is not a live Official or Grand Slam result.
- `model_battle_sample/` uses `run_eeab67d58b994ca7.eslams`, a short built-in
  first-legal versus first-legal chess run. `run_d48ff364a0b949df` is not in this tree.

Scratch harness state and exploratory local runs are intentionally omitted.
