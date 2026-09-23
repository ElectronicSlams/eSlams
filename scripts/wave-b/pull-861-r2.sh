#!/usr/bin/env bash
# =============================================================================
# HOLD — DO NOT EXECUTE AGAINST PRODUCTION
# =============================================================================
#
# Wave B tier A stub. Copies the 861 SUCCESS `.eslams` keys from
# `eslams-artifacts-prod` only after every gate below is opened by a human
# on the ops box.
#
# STATUS 2026-09-23: HOLD.
#   Closed until ALL of these are true, and none of them are true because
#   a workflow said so:
#     1. Explicit founder go for this R2 pull
#     2. Scrub checklist accepted (publish still happens later, after scrub)
#     3. A-EX cap locked at <=50 unless the founder raised it
#
# Defaults:
#   DRY_RUN=1
#     Print the plan. Do not call wrangler. Do not download objects.
#   KEYS_FILE is unset.
#     The 861-line r2key list is NOT in git. Point KEYS_FILE at the ops-box file.
#   OUT_DIR is unset.
#     A real pull must write outside this repository.
#
# A real pull requires all of:
#   WAVE_B_FOUNDER_GO=yes
#   WAVE_B_R2_PULL_HOLD=release
#   DRY_RUN=0
#   KEYS_FILE=/abs/path/to/extract-861-r2keys.txt    # exactly 861 keys
#   OUT_DIR=/abs/path/outside/this/repo
#
# FORBIDDEN:
#   - GitHub Actions or any other CI (this script exits on CI / GITHUB_ACTIONS)
#   - wrangler d1 execute / export / delete
#   - full-bucket sync, aws s3 sync, rclone copy of eslams-artifacts-prod
#   - deleting D1 rows or R2 objects
#   - committing pulled objects or the jsonl extract
#
# This file is a stub with the brakes on. Opening the brakes is a founder act,
# performed by hand, after docs/wave-b/README.md steps are cleared.
# =============================================================================

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUCKET="${BUCKET:-eslams-artifacts-prod}"
KEYS_FILE="${KEYS_FILE:-}"
OUT_DIR="${OUT_DIR:-}"
DRY_RUN="${DRY_RUN:-1}"
WAVE_B_R2_PULL_HOLD="${WAVE_B_R2_PULL_HOLD:-hold}"
WAVE_B_FOUNDER_GO="${WAVE_B_FOUNDER_GO:-no}"
EXPECTED_KEYS=861

say() { printf '%s\n' "$*"; }
die() { printf 'REFUSED: %s\n' "$1" >&2; exit "${2:-2}"; }

# CI must never pull or delete. Dry-run from a workflow is also refused so a
# later edit cannot flip DRY_RUN inside GitHub Actions.
if [[ -n "${CI:-}" || -n "${GITHUB_ACTIONS:-}" || -n "${GITLAB_CI:-}" || -n "${BUILDKITE:-}" \
   || -n "${CIRCLECI:-}" || -n "${TF_BUILD:-}" || -n "${JENKINS_URL:-}" || -n "${TRAVIS:-}" \
   || -n "${BUILD_NUMBER:-}" ]]; then
  die "Wave B R2 pull is forbidden in CI. Do not call this script from a workflow." 3
fi

say "================================================================"
say "HOLD  Wave B tier A R2 pull stub"
say "      bucket: ${BUCKET}"
say "      DRY_RUN=${DRY_RUN}  WAVE_B_R2_PULL_HOLD=${WAVE_B_R2_PULL_HOLD}  WAVE_B_FOUNDER_GO=${WAVE_B_FOUNDER_GO}"
say "      No D1 export. No D1 delete. No full-bucket copy."
say "================================================================"

if [[ "${BUCKET}" != "eslams-artifacts-prod" ]]; then
  die "BUCKET must stay eslams-artifacts-prod for this stub (got: ${BUCKET})."
fi

key_ok() {
  local key="$1"
  [[ "${key}" == *.eslams ]] || return 1
  [[ "${key}" != /* ]] || return 1
  [[ "${key}" != *".."* ]] || return 1
  [[ "${key}" != *$'\t'* ]] || return 1
  [[ "${key}" != *"://"* ]] || return 1
  [[ "${key}" != *'$'* && "${key}" != *'`'* && "${key}" != *';'* ]] || return 1
  return 0
}

count_keys() {
  local n=0 key
  while IFS= read -r key || [[ -n "${key}" ]]; do
    [[ -z "${key}" ]] && continue
    n=$((n + 1))
  done < "${KEYS_FILE}"
  printf '%s\n' "${n}"
}

if [[ "${DRY_RUN}" != "0" ]]; then
  say "DRY-RUN (default). wrangler will not be called. No objects transferred."
  if [[ -n "${KEYS_FILE}" && -f "${KEYS_FILE}" ]]; then
    n="$(count_keys)"
    say "Keys file: ${KEYS_FILE} (${n} non-empty lines; release mode requires ${EXPECTED_KEYS})."
    say "Would run, after founder go: wrangler r2 object get ${BUCKET}/<key-ending-in.eslams> --file <OUT_DIR>/<key>"
  else
    say "Keys file is not in git. Set KEYS_FILE to the ops-box extract-861 r2key list."
  fi
  say "HOLD remains in force. Founder go + scrub checklist + A-EX cap are still required."
  exit 0
fi

[[ "${WAVE_B_FOUNDER_GO}" == "yes" ]] || die "founder go is closed (set WAVE_B_FOUNDER_GO=yes only after an explicit founder instruction)."
[[ "${WAVE_B_R2_PULL_HOLD}" == "release" ]] || die "pull HOLD is still engaged (set WAVE_B_R2_PULL_HOLD=release only with founder go)."
[[ -n "${KEYS_FILE}" && -f "${KEYS_FILE}" ]] || die "KEYS_FILE must be the ops-box r2key list. It is not committed in this repo."
[[ -n "${OUT_DIR}" ]] || die "OUT_DIR must be an absolute path outside this repository."
[[ "${OUT_DIR}" == /* ]] || die "OUT_DIR must be absolute."

case "${OUT_DIR}" in
  "${ROOT}"|"${ROOT}"/*)
    die "OUT_DIR is inside the git repo (${ROOT}). Write outside the repo."
    ;;
esac

n="$(count_keys)"
[[ "${n}" -eq "${EXPECTED_KEYS}" ]] || die "key count is ${n}; this stub only pulls the locked ${EXPECTED_KEYS} tier A objects."

# Validate every key before the first download so a bad list cannot partial-pull.
while IFS= read -r key || [[ -n "${key}" ]]; do
  [[ -z "${key}" ]] && continue
  key_ok "${key}" || die "refusing key that is not a relative .eslams object path."
done < "${KEYS_FILE}"

command -v wrangler >/dev/null 2>&1 || die "wrangler is not on PATH. Install it on the ops box; do not run this from CI."

say "RELEASE path entered by operator env. Pulling ${n} objects into ${OUT_DIR}."
say "This still does not delete D1 or R2, and it does not list the bucket."

i=0
while IFS= read -r key || [[ -n "${key}" ]]; do
  [[ -z "${key}" ]] && continue
  i=$((i + 1))
  dest="${OUT_DIR}/${key}"
  mkdir -p "$(dirname "${dest}")"
  say "[${i}/${n}] wrangler r2 object get ${BUCKET}/${key} --file ${dest}"
  wrangler r2 object get "${BUCKET}/${key}" --file "${dest}"
done < "${KEYS_FILE}"

say "Done. Pulled ${i} objects into ${OUT_DIR}. Scrub before any publish. D1 delete stays closed."
