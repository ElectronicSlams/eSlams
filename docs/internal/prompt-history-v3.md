# Prompt history v3 internal successor

Version0.7.0.dev5+prompthistory.1 succeeds the frozen consolidated21c3ebc.
The new default Core prompt content version is eslams.core.prompt.v3: every
supplied history record is retained. ModelProviderAgent already retained all
supplied ActRequest history; this closes the separate core_contract.prompt_package
entrypoint's implicit24-record projection. No running/frozen research source,
model request, route, policy, budget or result is modified by this branch.

`prompt_package(..., history=records)` defaults to v3. Explicit
`prompt_version="eslams.core.prompt.v2"` reproduces the old last24-record package,
promptHash and tokenEstimate exactly for valid inputs. Unknown versions reject
before game callbacks. v3 validates a list of finite JSON records before invoking
observation/legal-action callbacks; an invalid earlier record cannot be hidden
by slicing it away. The caller still supplies actor-authorized public history:
this quantity change is not a permission to include private state or reasoning.
Observation projection, legal actions, output schema and game state are unchanged.

The CLI accepts --history pointing to a JSON object containing only a history
list, and --prompt-version selects exact v3 or legacyv2 semantics. The capability
response advertises the current default and both supported content versions.
The generic prompt package envelope remains eslams.core.prompt_package.v2 and its
structural schema bundle remainsv6: the fields did not change. Content semantics
are versioned by promptVersion, not by assuming the envelope version fixes prompt
bytes. Schema examples now advertise the current default. TypeScript consumers
still use the same structural string fields; CoreLite's separate v2 metadata is
not relabeled or represented as new prompt-generator parity.

Even empty/short-history prompts have a new hash because promptVersion changes.
A new comparison cohort must pin the same prompt treatment in all arms. Existing
cohorts must use their exact old package or explicitly selectv2; no historical
prompt or result is rewritten. Provider context limits and host input quotas
remain explicit independent constraints; there is no silent truncation to fit an
endpoint and no claim of infinite provider capacity.

## Shared acceptance

fixtures/prompt_history/prompt_versions.v1.json contains four synthetic history
lengths0/24/25/40 with pre-change21c3ebc v2 packages and successorv3 packages.
These formatting fixtures are not actual game trajectories or model responses.
Independent implementations must preserve legacy bytes/hashes, retain every v3
record, reject unknown versions, keep observation/legality projection unchanged
and record the selected version. The fixture is a proposed paired target until
independent review and Rust-owner implementation/acceptance; Python PASS is not
Rust parity. No private Rust implementation is included.

25 new keyless tests cover default/full history, explicit legacy packages,
unsupported versions and invalid history before callbacks, non-finite early
records, public/private-game view invariance, capability discovery and CLI
compatibility. The baseline exposes the old truncation and lacks the new explicit
APIs; its25failures are not25separate historical bugs. Full Core/static/package,
installed-wheel, native C4 and numeric replay results are recorded separately.
Independent review, Linux/new-image adoption and full runtime release gates remain.


Five additional virtual-wait regressions close the missing direct Retry-After
acceptance evidence: the pinned a935245 adapter rejects a complete definitive429
with Retry-After10 at its old5second limit, while the successor waits virtually
and performs exactly the caller-enabled second mock attempt. Explicit no-deadline
Retry-After110 and finite-deadline refusal are covered, as are the two bounds of
the implemented optional randomized-linear jitter. No real sleep/provider call
occurs. This does not claim the historical full-jitter/exponential proposal or a
distributed provider limiter is implemented.
