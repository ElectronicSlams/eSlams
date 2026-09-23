# Core Low F7–F10 status

Index only. This file records where the residual Low findings from the
2026-09-23 Core review live. It is not a second code change.

Implementation is draft
[#26](https://github.com/ElectronicSlams/eSlams/pull/26),
taken from review
[#16](https://github.com/ElectronicSlams/eSlams/pull/16).
[#26](https://github.com/ElectronicSlams/eSlams/pull/26)
is still a draft: no merge and no deploy.

A Local Artifact is not Official and is not a Grand Slam. Those verification
levels come only from controlled eSlams infrastructure.

## Findings in #26

- **F7** — Replay zip extraction uses the artifact path guard, and unknown Chess FEN text is escaped before it enters replay HTML.
- **F8** — `eslams agent serve` defaults to localhost (`127.0.0.1`).
- **F9** — Ordinary CI actions are pinned to full SHAs with `contents: read`; `.env` is ignored; Gemini live model lists send the API key in a header.
- **F10** — `docs/PROTOCOL.md` cites provider receipt v2; `packages/core-lite` stays unpublished until its metadata is bumped.

## Related drafts

Links by number only. This page does not rewrite those drafts.

- [#16](https://github.com/ElectronicSlams/eSlams/pull/16) — review
- [#21](https://github.com/ElectronicSlams/eSlams/pull/21) — F1–F6
- [#23](https://github.com/ElectronicSlams/eSlams/pull/23) — founder gates
- [#25](https://github.com/ElectronicSlams/eSlams/pull/25) — contributor holds
- [#24](https://github.com/ElectronicSlams/eSlams/pull/24) — Wave A path
