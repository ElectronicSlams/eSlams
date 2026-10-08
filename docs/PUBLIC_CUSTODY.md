# Artifact custody and claims

| Object or action | Meaning and custody |
| --- | --- |
| Local runner archive | Private audit material, including hidden game state and agent I/O. Share only with an intended private auditor. |
| Public replay export | A validated, allowlisted public projection. Inspect every public field before sharing; validation is not a general PII scrubber. |
| Publication bundle | Deterministic evidence rows and public replay files. `official-proof` is a format name, not a trust grant. |
| Local signature | The configured keyholder signed the file table. Trust depends on an independently trusted public key and the claimed execution context. |
| Official or Grand Slam claim | Requires the controlled infrastructure and independently established trust policy for that claim. A label, local test pass or uploaded fixture does not establish it. |
| Green developer tests | Evidence about a source change. They are not an artifact and do not confer a match verification level. |

Core's public export and Platform's private intake serve different audiences.
A hosted application must distinguish them before accepting an upload. Never
publish a raw runner bundle merely because it validates. Authentication alone
does not establish that an intake will keep uploaded private data private.

Core does not implement archive-host provisioning, storage downloads, database
deletion, dataset publication or hosted product retirement. This consolidation
does not declare the Official suite retired or authorize disclosure of hidden
eval seeds. Draft archive census counts and proposed destinations were not
verified against their source objects and are excluded from the public guide.

No Hugging Face URL is treated as an official download source here. Before
adding one, establish ownership, verify the exact dataset/card/Collection URL,
record the producer version and checksums, review disclosure permissions and
compare the bytes. Keep unmatched or unreviewed material private. A future
mirror becomes `dual_home: true` only after both homes are verified.

The [security policy](../SECURITY.md), [artifact contracts](ARTIFACTS.md) and
[sample inventory](SAMPLE_CLASSIFICATION.md) describe the implemented boundaries.
