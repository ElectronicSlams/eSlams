# Local eval publication shape

`local_eval_fixture.eslams` is an unsigned, complete, deterministic tic-tac-toe
Local fixture. `publication_bundle/` uses the `official-proof` format to exercise
an ingestion shape. It grants no Official or Grand Slam trust. Its proof-row
eligibility and aggregate leaderboard eligibility remain false. `plan.json` is
a keyless Battlefield plan for illustration, not a hidden Official suite.

```bash
eslams validate sample_runs/model_eval_sample/local_eval_fixture.eslams --profile runner-bundle
eslams publish validate sample_runs/model_eval_sample/publication_bundle --json
# Expected nonzero exit: this unsigned Local fixture is not an Official bundle.
eslams validate sample_runs/model_eval_sample/local_eval_fixture.eslams --profile official-bundle
```

The first two commands pass on the proposed source. Official validation fails
with `runner_signature_missing`. The former 0.2.0 `official_signed.eslams` used
legacy HMAC signing and failed Official validation with
`runner_signature_legacy_untrusted`, not `unverified_missing_key`. It is removed
from the newcomer sample path; legacy-HMAC rejection remains covered in the
validator regression suite. Existing historical bytes remain in Git history.
