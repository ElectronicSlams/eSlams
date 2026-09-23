# @eslams/core-lite

Unpublished path-alias package. `tsconfig.json` maps `@eslams/core-contracts`
to the in-tree `packages/core-contracts` sources, which are package version
`0.6.1`. CI typecheck uses that alias, so it does not install this package
from the npm registry.

`package.json` is `0.6.1` and depends on `@eslams/core-contracts` `0.6.1`,
matching the in-tree contracts package. `"private": true` blocks an accidental
`npm publish`.

Do not `npm publish` `@eslams/core-lite` until a founder gate. This package is
not published to npm or PyPI. Python `eslams-core` is the published runtime.
