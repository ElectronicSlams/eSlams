# Core-lite

This in-tree TypeScript source package implements the `standard` tic-tac-toe
and connect-four rulesets. Python Core remains the official evaluation authority.
Both TypeScript packages are private and are not published to npm. They are
excluded from Python distributions; use a checkout and the provided path aliases.

`createInitialState(gameId, "standard", seed)` accepts a signed decimal seed
string within JavaScript's safe integer range, including zero. Invalid seeds,
unsupported games, and unsupported rulesets throw configuration errors. Python
supports larger integer seeds; Core-lite rejects these rather than rounding them.

`applyAction(state, action)` accepts integer moves, exact action-token strings,
and the contract's `actionId`, `action_id`, `token`, `compact`, or `payload`
wrappers. It returns structured errors for terminal, malformed, or stale-hash
states. It preserves its input snapshot. Scores use Python float formatting
when hashed; SHA-256 consumes UTF-8 bytes. Transport diagnostics are excluded
from the canonical state fields.

CI compiles the runtime and runs `scripts/verify_core_lite.py` against freshly
generated Python fixtures. The check compares every deterministic response field
for both games, wins/draws, all supported action forms, and zero/negative/large
safe integer seeds. Wall-clock timestamps, timing values, and error prose are
excluded. Core-lite provides the `ids` legal-action response and default public
compact observation; it does not expose Python's complete CoreStepRequest API,
deadlines, HTTP service, session signatures, or official-run artifact generation.
