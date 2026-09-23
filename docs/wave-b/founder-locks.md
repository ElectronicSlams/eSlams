# Founder locks — Wave B

## 2026-09-21 — public archive

The Official suite is **retired / historical**. Scrubbed `official-hidden` proofs
may go **public**. Spoil is accepted.

Still scrub before any publish:

- provider and API keys, Cloudflare and GitHub tokens, signing private keys
- signed gateway URLs and pre-signed URLs
- auth, Trinity, and session material
- PII (emails, IPs, account join keys)

Hugging Face is the public warehouse. GitHub holds samples and pointers, not
the full artifact tree (~28.7 GiB listed on R2).

This lock supersedes the earlier private-only framing for tiers B and C.
Residual private storage is only for bytes that cannot be scrubbed, with a
path and a reason code.

## 2026-09-23 — this change

Draft documentation only.

- Do not merge until the founder says so.
- Do not deploy.
- Do not pull R2, query D1, export D1, or delete D1.
- Do not run wrangler against production.
- The R2 pull stays **HOLD** until an explicit founder go, with the scrub
  checklist accepted and the A-EX cap locked at ≤50.
- D1 delete stays closed until dual-home verification and a separate founder
  delete instruction.
- KEEP on D1: `arenasession` **136** and `platformmatch` **108**.
