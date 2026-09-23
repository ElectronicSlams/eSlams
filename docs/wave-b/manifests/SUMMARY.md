# extract-861 manifest summary

**Status:** counts only. The row extract and the r2key list stay on the ops box.
They are not in this repository.

| | |
| --- | --- |
| Generated | 2026-09-20 PT |
| Source | D1 `eslams-prod`, read-only |
| Filter | locked tier A SQL in [../tiers.md](../tiers.md) |
| Bucket | `eslams-artifacts-prod` |
| Pull | **HOLD** — [`scripts/wave-b/pull-861-r2.sh`](../../../scripts/wave-b/pull-861-r2.sh) defaults to dry-run |

## Counts

| | |
| --- | ---: |
| Rows | **861** |
| Distinct `arenaid` | **2** |
| Sum `sizebytes` | **1,191,331,447** (1.110 GiB) |

### `signaturestatus`

| Status | Rows |
| --- | ---: |
| `unsigned` | 856 |
| `signed` | 5 |

### `verificationlevel`

| Level | Rows |
| --- | ---: |
| `officialbenchmark` | 861 |

### `arenaid`

| Arena | Rows |
| --- | ---: |
| `arena_tic_tac_toe` | 860 |
| `arena_connect_four` | 1 |

## Left on the ops box

- `extract-861.jsonl` — one JSON object per row
- `extract-861-r2keys.txt` — one r2key per line

`scripts/wave-b/pull-861-r2.sh` reads whichever key list the operator passes as
`KEYS_FILE`. In release mode it refuses a list whose non-empty line count is
anything other than 861.
