# @eslams/core-lite

Unpublished path-alias package. `tsconfig.json` maps `@eslams/core-contracts`
to the in-tree `packages/core-contracts` sources, which are package version
`0.6.1`. CI typecheck uses that alias, so it does not install the version
declared below.

`package.json` is still `0.4.0` and depends on `@eslams/core-contracts`
`0.4.0`. That metadata does not match the contracts this tree typechecks.

Do not publish `@eslams/core-lite` until its version and dependency are bumped
to track `@eslams/core-contracts` `0.6.1`. This package is not published to
PyPI. Python `eslams-core` is the published runtime.
