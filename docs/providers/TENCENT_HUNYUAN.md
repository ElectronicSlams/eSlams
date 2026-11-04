# Tencent native Hunyuan

The `tencent-hunyuan:<model>` adapter (alias `hunyuan:<model>`) targets Tencent
Cloud's native text inference product. The existing `tencent`,
`tencent-tokenhub`, and `tencent-coding-plan` catalogue names retain their
existing meaning and do not dispatch to this adapter. They include models
from different products. There is no cross-product or model fallback.
An explicit nonblank model ID is required; bare provider aliases and empty or
whitespace-only model suffixes are rejected before inference.

## Product and lifecycle

Verified against official documentation on 2026-11-04:

| Contract | Evidence and adapter decision |
| --- | --- |
| Native text API | [`ChatCompletions`](https://cloud.tencent.com/document/product/1729/105701), version `2023-09-01`, POST `https://hunyuan.ai.tencentcloudapi.com/`. This is the current domain in the API description; older examples and SDK defaults use `hunyuan.tencentcloudapi.com`. No claim of live reachability is made. |
| Lifecycle | The same API document marks retirement for **2026-12-21 16:33:34** (timezone unspecified). Preflight always warns. The legacy console retirement notice is also present. |
| Region | Native `Region` is optional. Omit it by default; an explicit `TENCENTCLOUD_REGION` becomes `X-TC-Region`. No region or residency guarantee is inferred from omission. |
| Other direct APIs | Tencent's [OpenAI-compatible API](https://cloud.tencent.com/document/product/1729/111007) uses `https://api.hunyuan.cloud.tencent.com/v1/chat/completions` with a separately issued Bearer API key. Its migration notice directs new purchases and capabilities to TokenHub. This adapter never sends Cloud SecretId/SecretKey credentials to either product. |

## Configuration

Export credentials through your normal private environment mechanism. Core does
not load `.env` automatically; do not put actual values in tracked files.

- `TENCENTCLOUD_SECRET_ID` and `TENCENTCLOUD_SECRET_KEY` are required.
- `TENCENTCLOUD_TOKEN` optionally accompanies temporary STS credentials.
- `TENCENTCLOUD_REGION` is optional; it must be a region identifier.

The [common parameter contract](https://cloud.tencent.com/document/api/1729/101842)
specifies `X-TC-Action`, `X-TC-Version`, `X-TC-Timestamp`, optional region/token,
and signing service `hunyuan`. Timestamp skew beyond five minutes can fail
authentication. Temporary credentials use their temporary ID/key plus the token;
long-term credentials must omit the token.

The adapter implements [TC3-HMAC-SHA256](https://cloud.tencent.com/document/api/1729/101843).
It signs the UTF-8 HTTPX JSON request bytes, path `/`, empty query, content type,
host and lowercase action header. The UTC date determines credential scope
`date/hunyuan/tc3_request`. Signing happens after the shared concurrency/rate
guard, for every physical request. Gateway replacement is rejected because the
signed destination is fixed. Keys, tokens and Authorization never enter receipts.
Receipt identifiers matching configured primary/secondary credentials, embedded
credential values or recognizable credential shapes are discarded on success,
HTTP errors, malformed responses and partial-body failures before publication.
Raw and JSON-decoded/escaped action content is also checked for the selected
primary, secondary and temporary credentials before action parsing or repair.
Matching output is rejected without retry; sanitized usage evidence is retained.

Configuration preflight makes no network request:

```bash
eslams providers preflight --provider hunyuan --model hunyuan-a13b --arena tic-tac-toe
eslams run --arena tic-tac-toe --agent hunyuan:hunyuan-a13b --opponent first-legal --output-dir runs/hunyuan
```

The second command performs paid inference with configured credentials; it was
**not run** during implementation. `--live` preflight also performs inference
and requires separate operator authorization. No documented Models API is
assumed; account visibility remains unknown. Native model admission follows
0.7.0 advisory policy; no catalogue availability or official eligibility is invented.
Configuration readiness requires the primary/secondary credential pair, valid
optional settings, an explicit model and supported controls. Local rejection
reports `configuration_ready: false` without attempting inference.

## Controls, parsing and accounting

The [official request/response model definitions](https://github.com/TencentCloud/tencentcloud-sdk-python/blob/master/tencentcloud/hunyuan/v20230901/models.py)
provide the additional schema cross-check. The native request has no documented
`MaxTokens` field; an explicit output-token maximum is rejected before submission.
No framework output cap, total/read deadline, sampling value, reasoning effort
or reasoning budget is added by default. Explicit elapsed time limits continue
through the shared transport. Explicit temperature maps to `Temperature`.

`Model` is transmitted exactly as supplied. The two `Messages` contain the
standard system instructions and the full shared ActRequest prompt, including
all supplied history unless the operator explicitly selects a history window.
`Stream` and `EnableEnhancement` are false. No tools or search are requested.
Native context limits still apply; Tencent documents server-side leading-context
truncation when inputs exceed its model limit. Core does not trim to conceal it.

`auto` omits `EnableThinking`. Explicit enabled/disabled modes map to that field
only for exact `hunyuan-a13b`; other model/control combinations are rejected.
There is no arena-dependent reasoning policy. Tencent's
[data types](https://cloud.tencent.com/document/api/1729/101838) distinguish
`Message.Content` from `ReasoningContent`; only the former can supply an action.
Reasoning is never copied into outgoing messages or receipts.

Both documented non-streaming forms are accepted: a `Response` wrapper, or the
direct native result. Only one assistant message with `FinishReason: stop` is
accepted. Sensitive/moderation failures are refusals. Length/max-token signals
are conservatively treated as truncation, even though the native Choice table
currently enumerates only stop/sensitive/tool_calls. Unknown finish signals,
tool calls, malformed/duplicate JSON and SDK convenience shapes fail closed.

Native usage reads `PromptTokens`, `CompletionTokens`, and `TotalTokens` without
filling absent fields. Optional `PromptTokensDetails.CachedTokens` is a documented
decimal string; a validated value is retained. Reasoning counts and inclusion,
cache subdivision/inclusion, resolved model identity and USD cost remain unknown.
The API returns request/response IDs, not an attested model name. Request IDs
cannot prove a fixed backend. No other product's catalogue pricing is applied.

## Errors, retry and evidence

The [official error contract](https://cloud.tencent.com/document/api/1729/101847)
uses `Response.Error.Code/Message` and `RequestId`. Authentication, permission,
rate-limit, timeout, refusal and unavailable codes are classified before parsing
action text, including errors returned with HTTP 200. `ErrorMsg` is also treated
as an error when populated. Arbitrary error messages stay private. Observed usage
is retained alongside refusal/truncation/error outcomes; it does not make those
outcomes scoring-valid. HTTP status, safe request ID and unknown accounting
survive failures. Partial-body evidence uses the shared transport custody rules.

Default retries and action repairs remain zero. Native errors are never
automatically replayed, including 429 with an explicit retry budget: an engine
limit/error and request ID cannot prove that generation never started. No timeout
or 5xx is replayed. Each physical attempt uses the existing invocation-scoped
receipt and sanitized attempt ledger.

`tests/fixtures/provider/tencent_hunyuan_chat_completions_success.json` follows
the wrapped success example in the native API document: the answer alone was
replaced with synthetic legal-action JSON. It is documentation-derived, not a
live capture. The disclaimer is preserved in the fixture. Fault injections in
`tests/test_tencent_hunyuan.py` retain the native envelope and include HTTP/body
errors, malformed data, missing usage, privacy and actual transmitted-byte
signature verification through HTTPX MockTransport. No paid inference or real
credentials were used.
