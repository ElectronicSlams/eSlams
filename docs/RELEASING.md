# Python 0.8.0 release handoff

Build and verification run in an isolated operator/server workspace. The one approved
hosted job only verifies the handoff and publishes through the existing PyPI
trusted publisher; it does not install Core, build packages or run the suite.
This release includes verified chess continuation and the already reviewed
Krutrim adapter. Stronger OpenRouter backend enforcement remains deferred.
Invalid raw diagnostic score fields are retained as documented in README.

## Server side

Use a clean exact commit checkout and an isolated Python environment containing
its declared development/build requirements. Provide Node and TypeScript 5.9.3.
Run `scripts/server_release_check.py --out <new-evidence-directory> --tsc <tsc.js>`.
It records commands, statuses, source identity and artifact hashes. The previously
denied elapsed-deadline listener fixture remains excluded; no real-transport
acceptance is inferred. Two CLI failure fixtures use explicit offline mocks.
Package tests reuse the installed build backend with `--no-isolation`.

All admitted checks must pass, including wheel/sdist consumers outside the
checkout. Failures stop the process; do not edit expectations, skip failing
checks, replace historical goldens or retry ambiguous paid inference to obtain a
release. No paid inference is part of the release checks.

Then run `scripts/build_publish_bundle.py` with that receipt and distribution
folder. It rejects missing/failed checks and changed artifacts, binds package
version and source provenance, and creates exactly one new
`eslams-core-0.8.0-publish.zip`. The manifest contains only source/version,
verification-receipt digest and the two artifact filenames/sizes/digests. Keep
full logs and dependency receipts separately; do not upload secrets or unrelated
research/model data.

## Publisher-only side

After independent review and server acceptance, update the repository with the
reviewed source and matching `v0.8.0` tag. Commit CI-skip instructions prevent
ordinary hosted push/PR CI; do not invoke other hosted workflows. Keep the
release in draft while publishing. Upload the sealed bundle to that draft,
independently verify its digest, and explicitly dispatch `publish.yml` **on the
v0.8.0 tag** with draft release ID, asset ID and bundle SHA256. There is no
release-event trigger or historical default ref in the new publisher workflow.
Do not invoke the old rebuilding workflow.

The hosted verifier checks the authenticated draft asset metadata, exact tag and
source commit, complete bundle hash, closed manifest, both artifact hashes,
package metadata and embedded source provenance. It rejects duplicate/path/link
members and bounded-expansion violations. It writes only the two distributions
inside the mounted workspace for the pinned PyPA Docker action. It never imports
or executes Core/build code. GitHub CLI handles authenticated asset redirects;
no custom code forwards a repository token to another host.

The job fails if PyPI 0.8.0 already exists or absence cannot be established. The
existing `pypi` environment and job-local `contents:write` / `id-token:write`
permissions are retained. Draft asset reads require the existing contents scope;
the job does not perform repository writes. Its dispatch is now restricted to
the exact `v0.8.0` tag, and no new persistent credential or publisher registration is created.
OIDC authentication failure is a blocker, not permission to create credentials
or broaden trust. Do not dispatch a replacement job blindly after a partial
upload; inspect PyPI file hashes and reconcile first.

After success, verify both public PyPI files match the server hashes, install
from PyPI in a fresh environment, and check version/provenance/schema/CLI smoke.
Only then publish the GitHub release notes. No cross-file atomic upload guarantee
is claimed. Record actual workflow run, final source commit, package hashes,
installation receipt and release URL. A successful Python publication is not a
Platform rollout or a Rust parity claim.
