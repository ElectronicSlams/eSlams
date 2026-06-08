Model Battle Sample
===================

This sample demonstrates the model-battle publication shape using the clean
Cursor harness chess run `run_d48ff364a0b949df`.

Contents:

- `run_d48ff364a0b949df.eslams`: raw runner bundle from the completed harness
  run.
- `plan.json`: deterministic battle plan for the two harness models on chess.
- `publication_bundle/`: exported `battlefield-sample` bundle for
  Platform-style ingestion.

Why this run was selected:

- both player provider statuses are `ok`;
- no agent errors were recorded;
- no fallback actions were used;
- deterministic replay validation passes.

Validation:

```bash
python3 -m eslams.cli validate sample_runs/model_battle_sample/run_d48ff364a0b949df.eslams
python3 -m eslams.cli publish validate sample_runs/model_battle_sample/publication_bundle --json
```
