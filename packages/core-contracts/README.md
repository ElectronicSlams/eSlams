# Core contracts

Generated TypeScript source contracts for Python Core 0.6.2. This private,
in-tree package is not published to npm or included in Python distributions.
Core-lite's tsconfig resolves it through the checked-in source path alias.
Type-check with the TypeScript command documented in CONTRIBUTING.md.

Recovery wire contracts are generated from the closed Python schemas with
`PYTHONPATH=src python scripts/generate_board_recovery_types.py`; add `--check`
to detect drift without writing. See [board recovery](../../docs/BOARD_RECOVERY.md)
for the permanent non-scoring and historical-uncertainty boundaries.
