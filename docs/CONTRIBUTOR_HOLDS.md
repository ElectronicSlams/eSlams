# Contributor holds

Short hygiene for people and agents working in this repository. Report
vulnerabilities through [SECURITY.md](../SECURITY.md). This page does not
change open pull requests.

## Secrets

Never commit secrets. That includes `.env` files, API keys, gateway signed
URLs, and Trinity or other auth material. Read credentials from the
environment only. Do not put them in CLI examples, fixtures, artifacts,
receipts, or docs.

## Version pin

Public docs and examples should prefer the pin `eslams-core==0.6.1`.

## Local runs

A Local Artifact or a lab run is not Official and not Grand Slam. Those
verification levels come only from controlled eSlams infrastructure. See
[Verification Posture](../README.md#verification-posture) in the README.

## GitHub access

Do not invite `cursoragent`, or a similar agent account, as a GitHub
collaborator.

## Agent holds

From an agent, do not merge, deploy, or change DNS. Do not pull R2, delete
D1, upload to Hugging Face, or create a Hugging Face org.

Founder gates for those holds are indexed in
[#23](https://github.com/ElectronicSlams/eSlams/pull/23).

## Runner HTTP

Do not bind runner HTTP to a public interface unless the authorization in
[#21](https://github.com/ElectronicSlams/eSlams/pull/21) is in place. This
page only points at that pull request.

## Related drafts

- [#24](https://github.com/ElectronicSlams/eSlams/pull/24) — Wave A lab path
- [#22](https://github.com/ElectronicSlams/eSlams/pull/22) — lab-pack honesty
