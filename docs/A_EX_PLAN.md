# A-EX teaching-fail plan (cap ≤50)

**Status: HOLD.** This page locks the selection rules for tier A-EX. It does
not curate rows, pull objects, or publish anything.

Do not pull R2. Do not query, export, or delete D1. Do not run wrangler.
Do not upload to Hugging Face. A candidate list is a local JSONL file an
operator already has. This repository does not contain that file.

Pin: `eslams-core==0.6.1`. The Wave B census and the 861-row canary stay on
the ops runbook ([PR #20](https://github.com/ElectronicSlams/eSlams/pull/20)).
This page is only the A-EX cap those notes left as a one-paragraph rule.

## What a row is

A-EX is a teaching set of **partial** and **failed** runs. It is not the 861
SUCCESS canary (860 tic-tac-toe + 1 connect-four). A row that would pass the
tier A SUCCESS filter does not belong here.

Each selected row is labeled `outcome=partial` or `outcome=failed`. It may
fail SUCCESS validation. That is the point. It is still a Local Artifact
example, not an Official result and not a Grand Slam result.

## Locked checks

`python -m eslams.public_archive candidates.jsonl` reads one local file and
prints violations. It does not download artifacts. `--ready` is the lock an
operator uses when the set is finished, not while drafting.

```text
cap: 50
ttt_timeout_keep: 1
ready_max_per_arena: 15
ready_min_arenas: 3
```

| Check | When |
| --- | --- |
| At most **50** rows | Always. The founder raises this cap; the checker does not. |
| `outcome` is `partial` or `failed` | Always. `success` is tier A, not A-EX. |
| `scrub` is `clean` | Always. Unscrubbed rows are not selectable. |
| No secret field names, signed URLs, or secret-like object keys | Always. |
| At most **one** tic-tac-toe `timeout` | Always. Near-duplicate tic-tac-toe timeouts stay out. |
| Both outcomes, at least **3** arenas, at most **15** rows in one arena | `--ready` only. |

`sha256`, when present, is 64 lowercase hex characters. Object keys are
relative paths with no scheme and no query string. The checker does not prove
that a digest matches an object in a bucket.

A draft list may be skewed. It still cannot exceed 50 or keep a second
tic-tac-toe timeout. `--ready` refuses a locked set that is still one arena,
one outcome, or a tic-tac-toe pile larger than 15.

## Suggested mix

Quotas below are guidance for whoever curates after the pull HOLD opens.
The checker enforces the locked checks, not these suggested maximums.

| Teaching point | Suggested max | Label |
| --- | --- | --- |
| Completed run with agent errors or fallbacks | 15 | `outcome=partial` |
| Illegal action or failed validation | 10 | `failure_class=illegal` or `invalid` |
| Timeout, including the single tic-tac-toe example | 10 | `failure_class=timeout` |
| Other arenas, to reach the diversity lock | remainder | any non-success outcome |
| Scrubbed `queuefailures` rows (`retrying` at the 2026-09-20 snapshot; 6 rows) | up to those that scrub | `failure_class=queue` |

Skip raw secret paths. Skip a second tic-tac-toe timeout even when the
suggested timeout slot is not full.

## Still closed

Curation runs only after tier A is in hand, the scrub checklist is accepted,
and the founder has opened the R2 pull. This page does not open that gate.
Empty input is a valid draft: nothing has been selected. There is no A-EX
pack in git.
