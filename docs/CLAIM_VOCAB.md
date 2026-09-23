# Claim vocabulary

Short labels so a lab user does not over-claim a local run. These three words
are already used in Core docs. This page does not add a product surface, a Hub
URL, a sample run id, or a second implementation of F7–F10.

A passing laptop check is a **Local Artifact**. It is not **Official** and it
is not a **Grand Slam**.

## Local Artifact

What a developer gets from a local Core run on `eslams-core==0.6.1`: `eslams
run`, `eslams validate`, a green `pytest` on this checkout, or the documented
keyless smoke commands.

That result is a proof you can inspect on the machine that produced it. A
green unit suite is a developer check on the public engine. It does not raise
the verification level.

```bash
pip install eslams-core==0.6.1
```

## Official

Reserved for the platform Official path and the retired public leaderboard
path. Local green is not Official.

The public leaderboard and the Official suite are retired and historical.
That retirement stays on its own draft. This page does not rewrite it and
does not reopen that path.

## Grand Slam

A tournament and product claim. A local run, a pytest pass, or the
`eslams-core==0.6.1` pin does not imply it. Only controlled eSlams
infrastructure can confer that claim. This page does not describe how to
produce one.

## Same work, different words

| You did this | You may say | You may not say |
| --- | --- | --- |
| Local `eslams run`, validate, pytest, or keyless smoke on `eslams-core==0.6.1` | Local Artifact | Official, Grand Slam |

The README verification posture is the boundary: Core creates Local Artifact
proof packages. Official and Grand Slam verification levels come only from
controlled eSlams infrastructure.

## Holds

From this open-source repository: no merge, no deploy, no DNS change, no R2
pull, no D1 query or delete, and no Hugging Face org, dataset, Collection, or
Space create or upload. The Hugging Face org `ElectronicSlams` is not live.
This page does not invent a Hub URL.

Do not rewrite #19, #20, or #21. Those drafts stay as written.

F7–F10 code lives only on #26. This page does not re-implement that work, and
it is not a Workers deploy doc or a Platform F3 doc.

## Related drafts

Pointers by number only. This page does not restate those drafts.

| PR | Role |
| --- | --- |
| [#27](https://github.com/ElectronicSlams/eSlams/pull/27) | Public vs private Core surface |
| [#24](https://github.com/ElectronicSlams/eSlams/pull/24) | Wave A lab path |
| [#29](https://github.com/ElectronicSlams/eSlams/pull/29) | Local test and smoke |
| [#22](https://github.com/ElectronicSlams/eSlams/pull/22) | Lab-pack honesty |
| [#28](https://github.com/ElectronicSlams/eSlams/pull/28) | F7–F10 status index |
| [#26](https://github.com/ElectronicSlams/eSlams/pull/26) | F7–F10 implementation (sole code PR; do not re-implement) |
