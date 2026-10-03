# Backlog consolidation

This is a work-in-progress resolution record for one consolidation PR. Original
issues and PRs remain open until their required behavior, disposition and
verification are demonstrated. No release is published by this work.

The original baseline is 275 passing collected cases / 243 test functions and
85.332886% line coverage over `src/eslams`. Final coverage
must be compared using the same scope; coverage gains cannot substitute for
retaining trust, privacy, provenance and behavioral checks. Test removal is
tracked explicitly against the original suite, with necessary new regression
coverage recorded separately.

## Completed implementation awaiting final integration gates

- #75: exports refuse existing/input-alias destinations and install staged
  output after success. Regression checks preserve unrelated files, reject
  working-directory/source/symlink destinations and exercise writer conflicts.

- #76: replay/golden exports require explicit file overwrite; replay refuses input
  and hardlink aliases and writes outside expanded artifacts.
- #173: normal replay rejects an ignored extra positional argument while
  retaining the validate-public compatibility command.

- #162 / #183: shared bounded archive extraction and cleanup now cover validation,
  replay and public export. Unsupported existing files are distinguished from
  missing files. This incorporates and extends the archive part of PR #26.

- #57 / #174: console/module entry points share expected-error reporting, debug
  tracebacks and clean termination when an output pipe closes early. The actual
  installed-wheel command remains a final integration gate (revised PR #217).

- #138 / #144 / #176: artifact writing stages complete outputs, rolls back
  failed replacements, propagates traversal/stat errors and uses fixed portable
  ZIP member timestamps. This incorporates PR #161 with additional symlink and
  failure safeguards. Native OS/Python matrix checks remain outstanding.

- #121 / #125 / #153: fixture generation uses an owned temporary root and
  installs only the requested archive. Filenames no longer determine run IDs;
  explicit overwrite is available without deleting siblings or latest links.

- #172: global `--version` / `-V` prints the shared package version and exits
  successfully. Installed-wheel verification remains outstanding.

- #54: agent protocol test reports failure and exits 1 for unreachable,
  malformed or illegal-action endpoints, while retaining valid diagnostic
  artifacts and reporting action/error counts.

- #59 / #102: nonpositive turn caps are rejected; externally truncated games
  retain valid diagnostics while failing scoring eligibility. Validation rejects
  refreshed eligibility claims on a nonterminal replay. Declared arena horizons
  remain complete games; fixtures and positive provider tests now finish games.

Actual installed-wheel console/module checks passed outside the checkout on
macOS/Python 3.9 (11 checks at commit b651238). This resolves the local packaging
entry-point gate for #57 / #174 / #172 and PR #217; the final matrix remains.

- #175 / #194: runner shard ranges and time-budget integers are validated
  before any output is created; budgets are no longer silently clamped.

- #186: all planners reject malformed/excessive shard counts, bounded by
  workload and a ceiling of 1024, rather than silently clamping or generating
  unbounded empty shards.

- #55: mypy now targets the active interpreter. The documented command checks
  all 95 source modules on Python 3.9 and 3.12; explicit CI matrix targets remain.

Full suites pass on macOS/Python 3.9.6 and 3.12.13: 366 cases each. Repository
lint also passes with the Python 3.12 development environment. Native Windows,
Linux, other supported interpreters and final consumer checks remain gates.

- #101: action legality uses strict JSON type/value equality. Boolean/float
  aliases follow illegal-action policies consistently; provider receipts never
  claim an applied action when a fallback replaced the rejected response.
  Latest Python 3.9 full suite: 373 passing cases.

## Test reduction checkpoint

Removed 11 of the required 55 original cases: ten redundant family registry-only
checks and one obsolete zero-turn acceptance test, replaced by rejection checks. Retained Runner tests create the same named arenas and validate their
artifacts; the retained all-arena smoke now checks exact public-catalogue
membership. Full suite: 373 passing cases; line coverage 85.800901%, above the
85.332886% baseline. Each removal and retained check is recorded in the JSON
ledger. Another 44 original cases remain to be assessed and removed.

## Remaining work

All 148 original issues and 43 original PRs, with captured PR heads and
individual acceptance criteria, are tracked in [backlog-resolution.json](backlog-resolution.json).
Each pending entry must receive implementation or an evidence-based disposition.
Package/OS/consumer compatibility, coverage retention and repository closure
are final gates. A passing narrow test does not establish completion of the
overall backlog.
