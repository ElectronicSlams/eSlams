Model Battle Sample
===================

This sample demonstrates the model-battle publication shape using a clean
deterministic Core chess battle run.

Contents:

- `run_eeab67d58b994ca7.eslams`: raw runner bundle from a short built-in
  `first-legal` versus `first-legal` chess run.
- `plan.json`: deterministic battle plan for the two built-in agents on chess.
- `publication_bundle/`: exported `battlefield-sample` bundle for
  Platform-style ingestion.

Why this run was selected:

- both player provider statuses are local and deterministic;
- no agent errors were recorded;
- no fallback actions were used;
- deterministic replay validation passes.
- public replay display frames and publication eligibility fields are emitted
  by the Core 0.2.0 artifact writer.

Validation:

```bash
python3 -m eslams.cli validate sample_runs/model_battle_sample/run_eeab67d58b994ca7.eslams
python3 -m eslams.cli publish validate sample_runs/model_battle_sample/publication_bundle --json
```
