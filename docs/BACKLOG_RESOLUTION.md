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

## Remaining work

All 148 original issues and 43 original PRs, with captured PR heads and
individual acceptance criteria, are tracked in [backlog-resolution.json](backlog-resolution.json).
Each pending entry must receive implementation or an evidence-based disposition.
Package/OS/consumer compatibility, coverage retention and repository closure
are final gates. A passing narrow test does not establish completion of the
overall backlog.
