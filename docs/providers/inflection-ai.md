# Inflection AI direct adapter: verification blocked

Research date: 2026-11-04. Core baseline:
`270a863d10d57a0953f21924f1a0dd50159e6cf1` (0.7.0).

There is no verified native Inflection adapter in this change. The existing
`inflection` registry alias resolves to `inflection-ai`, but a catalogue
organization is not an inference transport. Preflight and discovery must
continue to report `provider_adapter_unavailable`; direct dispatch must fail
without selecting another provider. This work does not establish that Inflection
has discontinued its API.

## Official evidence and retrieval limits

Inflection's [October 7, 2024 enterprise announcement](https://inflection.ai/blog/enterprise)
announces a commercial API and links to
[developers.inflection.ai](https://developers.inflection.ai/). The announcement
does not specify an inference endpoint, authorization header, request/response
schema, model ID, usage accounting, or retry contract. The current
[Inflection website](https://inflection.ai/) remains accessible, but its product
description is not an API specification.

Attempts to read the official portal root,
[documentation](https://developers.inflection.ai/docs), and
[API reference](https://developers.inflection.ai/docs/api-reference) through web
retrieval failed (inaccessible URL / 502). Shell HTTPS retrieval returned a
proxy tunnel `403 Forbidden`, including one escalated public-document fetch.
These are observations from this execution environment, not attested HTTP
responses from Inflection's inference service. No credential was read or sent.

Public-document probes of `/llms.txt`, `/openapi.json`, `/docs/quickstart`, and
`/docs/api-reference/chat-completions` were also unsuccessful. Search did not
recover the contents of official portal pages. Third-party API profiles and
community adapters surfaced possible legacy and chat-completions routes, but
were not accepted as official contract evidence. A hostname containing a region
name is not evidence of a residency guarantee.

## Verification matrix

| Requirement | Verified evidence / unresolved requirement |
| --- | --- |
| Current direct service | Historical official commercial launch confirmed; current availability and onboarding unverified. |
| Endpoint and region | No current official inference URL, region selection, or residency policy retrieved. |
| Authentication | No verified header scheme, key source, or permission contract. |
| Exact model identity | No verified direct model/config IDs, aliases, or response attestation fields. Broker IDs must not be translated into guessed native IDs. |
| Request and full history | No verified roles, history/context representation, required parameters, or provider defaults. |
| Response | No verified non-streaming envelope, content extraction, completion status, refusal, or truncation fields. |
| Reasoning | No verified controls, defaults, or usage inclusion semantics. Missing documentation does not prove absence of reasoning. |
| Errors and retries | No verified native error envelope, rate-limit headers, retry guarantees, or idempotency. Core retains zero default retries. |
| Usage and cost | No verified token fields, cache/reasoning accounting, cost fields, or direct rate card. Missing accounting must remain unknown. |
| Privacy | No verified API-specific retention/residency terms; consumer Pi behavior must not be substituted. |

## Completion requirements

Obtain an accessible official specification or provider-supplied contract and
record its date and provenance before adding a transport or raw-wire fixtures.
Implement the adapter in provider-specific files with minimal dispatch,
credential, and preflight wiring. Preserve the exact selected model/provider,
all supplied history, safe bounded HTTP transport and invocation receipts.
Retain provider defaults unless the operator explicitly chooses a supported
control; do not introduce arbitrary output/time limits or game-specific
reasoning. Do not fall back to a broker or another model.

Then add documented raw-wire success fixtures and deterministic fault injection
for 400/401/403/404/429/5xx, timeout, malformed bodies, missing usage, identity
absence/mismatch, refusal, truncation, retry policy, and privacy. Test aliases
through CLI, preflight, discovery, and dispatch. Reject missing/blank model IDs
without selecting a default; reject unsupported explicit reasoning controls in
both preflight and transport. Test echoed primary and secondary credentials in
IDs/receipts on success, error, malformed-response, and partial-body paths.
No such wire tests are claimed
by this change: fabricating an envelope would defeat the verification gate.

`tests/test_inflection_unavailable.py` covers the current boundary without
network calls: all selected spellings remain unavailable, no fallback is
contacted, and unsuccessful direct dispatch cannot manufacture identity or
accounting. No version bump, shared transport rewrite, live inference, merge,
or release is part of this change.

The boundary tests also cover blank model choices and explicit reasoning
budgets: both remain blocked before any network call. Receipt request/gateway
IDs remain null. Response-path credential-echo tests require a verified adapter
and remain outstanding. Replace the unavailability tests when implementing the
documented transport, preserving their no-fallback and privacy guarantees.
