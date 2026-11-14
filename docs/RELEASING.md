# Python 0.8.1 proposed release handoff

This patch is not released. Publication is on hold pending owner confirmation of
the version and scope. The 0.8.1 change adds only an explicit native-horizon child
execution budget and v2 continuation lineage, preserving immutable historical
source pins and v1 readers. It changes no arena rules or model time/output policy.
Version-pinned publisher metadata is prepared consistently; no PyPI dispatch or
credential change is part of preparing this patch.

Build and verification run in an isolated operator/server workspace. GitHub
verified-asset delivery is separate from optional PyPI publication. The existing
publisher-only hosted job verifies its handoff; it does not install Core, build
packages or run the suite, and must not be dispatched for this held proposal.
The 0.8.0 base includes verified chess continuation and the already reviewed
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
`eslams-core-0.8.1-publish.zip`. The manifest contains only source/version,
verification-receipt digest and the two artifact filenames/sizes/digests. Keep
full logs and dependency receipts separately; do not upload secrets or unrelated
research/model data.

## GitHub delivery first, only after approval

The owner requested GitHub delivery first and deferred PyPI. After the owner
confirms this proposal's version/scope, independent review and all required
guarded checks must pass against the exact clean commit. Only then may an
authorized operator push reviewed source, create its matching `v0.8.1` tag and
draft release, and upload the checksum-verified wheel/sdist and release evidence.
Commit CI-skip instructions prevent ordinary hosted push/PR CI; do not invoke
other hosted workflows. Independently read back the asset identities and hashes,
then publish the GitHub release when authorized. The sealed bundle may accompany
the verified distributions, but uploading it does not authorize PyPI dispatch.

Document the exact source commit, package hashes, local/isolated verification
receipt and GitHub release URL. This is GitHub artifact delivery, not a claim of
PyPI availability, Platform rollout or Rust parity. PyPI success is not a
prerequisite for the owner's GitHub-first route. Platform must independently pin
and validate the published distributions and resulting runtime image.

## Optional PyPI publication: blocked, no retry authorized

The earlier PyPI publisher encountered an inactive-organization denial. Do not
dispatch or retry `publish.yml`, create credentials, or broaden publisher trust
as part of this patch. The owner will handle PyPI separately. The version-pinned
publisher metadata remains prepared for consistency, not permission to execute.

If the owner separately resolves that blocker and authorizes publication later,
the existing publisher-only workflow accepts only the reviewed tag, release/asset
IDs and sealed bundle digest. There is no release-event trigger or historical
default ref. Do not invoke the old rebuilding workflow.

The hosted verifier checks the authenticated draft asset metadata, exact tag and
source commit, complete bundle hash, closed manifest, both artifact hashes,
package metadata and embedded source provenance. It rejects duplicate/path/link
members and bounded-expansion violations. It writes only the two distributions
inside the mounted workspace for the pinned PyPA Docker action. It never imports
or executes Core/build code. GitHub CLI handles authenticated asset redirects;
no custom code forwards a repository token to another host.

The job fails if PyPI 0.8.1 already exists or absence cannot be established. The
existing `pypi` environment and job-local `contents:write` / `id-token:write`
permissions are retained. Draft asset reads require the existing contents scope;
the job does not perform repository writes. Its dispatch is now restricted to
the exact `v0.8.1` tag, and no new persistent credential or publisher registration is created.
OIDC authentication failure is a blocker, not permission to create credentials
or broaden trust. Do not dispatch a replacement job blindly after a partial
upload; inspect PyPI file hashes and reconcile first.

If a separately authorized PyPI publication later succeeds, verify both public
PyPI files match the server hashes, install
from PyPI in a fresh environment, and check version/provenance/schema/CLI smoke.
Add that distinct result to the already verified GitHub release evidence. No
cross-file atomic upload guarantee is claimed. Record the actual workflow run,
source commit, package hashes, installation receipt and PyPI status. A successful
Python publication is not a Platform rollout or a Rust parity claim.
