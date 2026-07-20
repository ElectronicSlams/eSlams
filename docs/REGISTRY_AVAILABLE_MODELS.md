# Catalogued provider models (registry snapshot)

Core tracks **90 canonical provider/author namespaces**. The original 69 curated organizations are joined by Cursor from a platform API-discovered model row and 20 author namespaces from the release-pinned OpenRouter text-model snapshot.

This file describes source-backed catalog identities, not direct-adapter or account availability. A model row means an upstream registry source or checked-in override documented the identity. Only `available_from_api=true` is an API verification signal, and public eSlams availability is controlled separately by the deployed platform catalog.

Generated with `python scripts/render_provider_registry_docs.py` from `models.generated.json`, `overrides.json`, and `REQUESTED_PROVIDER_ORGANIZATIONS`.

Registry snapshot: `2026-06-04T02:52:41Z`

Sources: models.dev, litellm

Catalogued rows: **2189** (3 with `available_from_api=true`)

Rows marked `available_from_api=false` are excluded. Legacy aliases normalize to the same canonical provider keys used by the public `/models/...` routes.

| Provider | Model |
| --- | --- |
| AI21 Labs | `j2-light` |
| AI21 Labs | `j2-mid` |
| AI21 Labs | `j2-ultra` |
| AI21 Labs | `jamba-1.5` |
| AI21 Labs | `jamba-1.5-large` |
| AI21 Labs | `jamba-1.5-large@001` |
| AI21 Labs | `jamba-1.5-mini` |
| AI21 Labs | `jamba-1.5-mini@001` |
| AI21 Labs | `jamba-large-1.6` |
| AI21 Labs | `jamba-large-1.7` |
| AI21 Labs | `jamba-mini-1.6` |
| AI21 Labs | `jamba-mini-1.7` |
| Amazon / AWS | `1024-x-1024/50-steps/bedrock/amazon.nova-canvas-v1:0` |
| Amazon / AWS | `1024-x-1024/50-steps/stability.stable-diffusion-xl-v1` |
| Amazon / AWS | `1024-x-1024/max-steps/stability.stable-diffusion-xl-v1` |
| Amazon / AWS | `512-x-512/50-steps/stability.stable-diffusion-xl-v0` |
| Amazon / AWS | `512-x-512/max-steps/stability.stable-diffusion-xl-v0` |
| Amazon / AWS | `ai21.j2-mid-v1` |
| Amazon / AWS | `ai21.j2-ultra-v1` |
| Amazon / AWS | `ai21.jamba-1-5-large-v1:0` |
| Amazon / AWS | `ai21.jamba-1-5-mini-v1:0` |
| Amazon / AWS | `ai21.jamba-instruct-v1:0` |
| Amazon / AWS | `amazon-nova/nova-lite-v1` |
| Amazon / AWS | `amazon-nova/nova-micro-v1` |
| Amazon / AWS | `amazon-nova/nova-premier-v1` |
| Amazon / AWS | `amazon-nova/nova-pro-v1` |
| Amazon / AWS | `amazon.nova-2-lite-v1:0` |
| Amazon / AWS | `amazon.nova-2-multimodal-embeddings-v1:0` |
| Amazon / AWS | `amazon.nova-canvas-v1:0` |
| Amazon / AWS | `amazon.nova-lite-v1:0` |
| Amazon / AWS | `amazon.nova-micro-v1:0` |
| Amazon / AWS | `amazon.nova-pro-v1:0` |
| Amazon / AWS | `amazon.rerank-v1:0` |
| Amazon / AWS | `amazon.titan-embed-image-v1` |
| Amazon / AWS | `amazon.titan-embed-text-v1` |
| Amazon / AWS | `amazon.titan-embed-text-v2:0` |
| Amazon / AWS | `amazon.titan-image-generator-v1` |
| Amazon / AWS | `amazon.titan-image-generator-v2` |
| Amazon / AWS | `amazon.titan-image-generator-v2:0` |
| Amazon / AWS | `amazon.titan-text-express-v1` |
| Amazon / AWS | `amazon.titan-text-lite-v1` |
| Amazon / AWS | `amazon.titan-text-premier-v1:0` |
| Amazon / AWS | `anthropic.claude-3-5-haiku-20241022-v1:0` |
| Amazon / AWS | `anthropic.claude-3-5-sonnet-20240620-v1:0` |
| Amazon / AWS | `anthropic.claude-3-5-sonnet-20241022-v2:0` |
| Amazon / AWS | `anthropic.claude-3-7-sonnet-20240620-v1:0` |
| Amazon / AWS | `anthropic.claude-3-haiku-20240307-v1:0` |
| Amazon / AWS | `anthropic.claude-3-opus-20240229-v1:0` |
| Amazon / AWS | `anthropic.claude-3-sonnet-20240229-v1:0` |
| Amazon / AWS | `anthropic.claude-haiku-4-5-20251001-v1:0` |
| Amazon / AWS | `anthropic.claude-instant-v1` |
| Amazon / AWS | `anthropic.claude-mythos-preview` |
| Amazon / AWS | `anthropic.claude-opus-4-1-20250805-v1:0` |
| Amazon / AWS | `anthropic.claude-opus-4-5-20251101-v1:0` |
| Amazon / AWS | `anthropic.claude-opus-4-6-v1` |
| Amazon / AWS | `anthropic.claude-opus-4-7` |
| Amazon / AWS | `anthropic.claude-opus-4-8` |
| Amazon / AWS | `anthropic.claude-sonnet-4-5-20250929-v1:0` |
| Amazon / AWS | `anthropic.claude-sonnet-4-6` |
| Amazon / AWS | `anthropic.claude-v1` |
| Amazon / AWS | `anthropic.claude-v2:1` |
| Amazon / AWS | `apac.anthropic.claude-3-5-sonnet-20240620-v1:0` |
| Amazon / AWS | `apac.anthropic.claude-3-5-sonnet-20241022-v2:0` |
| Amazon / AWS | `apac.anthropic.claude-3-haiku-20240307-v1:0` |
| Amazon / AWS | `apac.anthropic.claude-3-sonnet-20240229-v1:0` |
| Amazon / AWS | `au.anthropic.claude-haiku-4-5-20251001-v1:0` |
| Amazon / AWS | `au.anthropic.claude-opus-4-6-v1` |
| Amazon / AWS | `au.anthropic.claude-opus-4-8` |
| Amazon / AWS | `au.anthropic.claude-sonnet-4-5-20250929-v1:0` |
| Amazon / AWS | `au.anthropic.claude-sonnet-4-6` |
| Amazon / AWS | `bedrock/*/1-month-commitment/cohere.command-light-text-v14` |
| Amazon / AWS | `bedrock/*/1-month-commitment/cohere.command-text-v14` |
| Amazon / AWS | `bedrock/*/6-month-commitment/cohere.command-light-text-v14` |
| Amazon / AWS | `bedrock/*/6-month-commitment/cohere.command-text-v14` |
| Amazon / AWS | `bedrock/ap-northeast-1/1-month-commitment/anthropic.claude-instant-v1` |
| Amazon / AWS | `bedrock/ap-northeast-1/1-month-commitment/anthropic.claude-v1` |
| Amazon / AWS | `bedrock/ap-northeast-1/1-month-commitment/anthropic.claude-v2:1` |
| Amazon / AWS | `bedrock/ap-northeast-1/6-month-commitment/anthropic.claude-instant-v1` |
| Amazon / AWS | `bedrock/ap-northeast-1/6-month-commitment/anthropic.claude-v1` |
| Amazon / AWS | `bedrock/ap-northeast-1/6-month-commitment/anthropic.claude-v2:1` |
| Amazon / AWS | `bedrock/ap-northeast-1/anthropic.claude-instant-v1` |
| Amazon / AWS | `bedrock/ap-northeast-1/anthropic.claude-v1` |
| Amazon / AWS | `bedrock/ap-northeast-1/anthropic.claude-v2:1` |
| Amazon / AWS | `bedrock/ap-northeast-1/deepseek.v3.2` |
| Amazon / AWS | `bedrock/ap-northeast-1/minimax.minimax-m2.1` |
| Amazon / AWS | `bedrock/ap-northeast-1/minimax.minimax-m2.5` |
| Amazon / AWS | `bedrock/ap-northeast-1/moonshotai.kimi-k2-thinking` |
| Amazon / AWS | `bedrock/ap-northeast-1/moonshotai.kimi-k2.5` |
| Amazon / AWS | `bedrock/ap-northeast-1/qwen.qwen3-coder-next` |
| Amazon / AWS | `bedrock/ap-south-1/deepseek.v3.2` |
| Amazon / AWS | `bedrock/ap-south-1/meta.llama3-70b-instruct-v1:0` |
| Amazon / AWS | `bedrock/ap-south-1/meta.llama3-8b-instruct-v1:0` |
| Amazon / AWS | `bedrock/ap-south-1/minimax.minimax-m2.1` |
| Amazon / AWS | `bedrock/ap-south-1/minimax.minimax-m2.5` |
| Amazon / AWS | `bedrock/ap-south-1/moonshotai.kimi-k2-thinking` |
| Amazon / AWS | `bedrock/ap-south-1/moonshotai.kimi-k2.5` |
| Amazon / AWS | `bedrock/ap-south-1/qwen.qwen3-coder-next` |
| Amazon / AWS | `bedrock/ap-southeast-2/minimax.minimax-m2.5` |
| Amazon / AWS | `bedrock/ap-southeast-3/deepseek.v3.2` |
| Amazon / AWS | `bedrock/ap-southeast-3/minimax.minimax-m2.1` |
| Amazon / AWS | `bedrock/ap-southeast-3/minimax.minimax-m2.5` |
| Amazon / AWS | `bedrock/ap-southeast-3/moonshotai.kimi-k2.5` |
| Amazon / AWS | `bedrock/ap-southeast-3/qwen.qwen3-coder-next` |
| Amazon / AWS | `bedrock/ca-central-1/meta.llama3-70b-instruct-v1:0` |
| Amazon / AWS | `bedrock/ca-central-1/meta.llama3-8b-instruct-v1:0` |
| Amazon / AWS | `bedrock/eu-central-1/1-month-commitment/anthropic.claude-instant-v1` |
| Amazon / AWS | `bedrock/eu-central-1/1-month-commitment/anthropic.claude-v1` |
| Amazon / AWS | `bedrock/eu-central-1/1-month-commitment/anthropic.claude-v2:1` |
| Amazon / AWS | `bedrock/eu-central-1/6-month-commitment/anthropic.claude-instant-v1` |
| Amazon / AWS | `bedrock/eu-central-1/6-month-commitment/anthropic.claude-v1` |
| Amazon / AWS | `bedrock/eu-central-1/6-month-commitment/anthropic.claude-v2:1` |
| Amazon / AWS | `bedrock/eu-central-1/anthropic.claude-instant-v1` |
| Amazon / AWS | `bedrock/eu-central-1/anthropic.claude-v1` |
| Amazon / AWS | `bedrock/eu-central-1/anthropic.claude-v2:1` |
| Amazon / AWS | `bedrock/eu-central-1/minimax.minimax-m2.1` |
| Amazon / AWS | `bedrock/eu-central-1/minimax.minimax-m2.5` |
| Amazon / AWS | `bedrock/eu-central-1/qwen.qwen3-coder-next` |
| Amazon / AWS | `bedrock/eu-north-1/deepseek.v3.2` |
| Amazon / AWS | `bedrock/eu-north-1/minimax.minimax-m2.1` |
| Amazon / AWS | `bedrock/eu-north-1/minimax.minimax-m2.5` |
| Amazon / AWS | `bedrock/eu-north-1/moonshotai.kimi-k2.5` |
| Amazon / AWS | `bedrock/eu-south-1/minimax.minimax-m2.1` |
| Amazon / AWS | `bedrock/eu-south-1/minimax.minimax-m2.5` |
| Amazon / AWS | `bedrock/eu-south-1/qwen.qwen3-coder-next` |
| Amazon / AWS | `bedrock/eu-west-1/meta.llama3-70b-instruct-v1:0` |
| Amazon / AWS | `bedrock/eu-west-1/meta.llama3-8b-instruct-v1:0` |
| Amazon / AWS | `bedrock/eu-west-1/minimax.minimax-m2.1` |
| Amazon / AWS | `bedrock/eu-west-1/minimax.minimax-m2.5` |
| Amazon / AWS | `bedrock/eu-west-1/qwen.qwen3-coder-next` |
| Amazon / AWS | `bedrock/eu-west-2/meta.llama3-70b-instruct-v1:0` |
| Amazon / AWS | `bedrock/eu-west-2/meta.llama3-8b-instruct-v1:0` |
| Amazon / AWS | `bedrock/eu-west-2/minimax.minimax-m2.1` |
| Amazon / AWS | `bedrock/eu-west-2/minimax.minimax-m2.5` |
| Amazon / AWS | `bedrock/eu-west-2/qwen.qwen3-coder-next` |
| Amazon / AWS | `bedrock/eu-west-3/mistral.mistral-7b-instruct-v0:2` |
| Amazon / AWS | `bedrock/eu-west-3/mistral.mistral-large-2402-v1:0` |
| Amazon / AWS | `bedrock/eu-west-3/mistral.mixtral-8x7b-instruct-v0:1` |
| Amazon / AWS | `bedrock/invoke/anthropic.claude-3-5-sonnet-20240620-v1:0` |
| Amazon / AWS | `bedrock/moonshotai.kimi-k2-thinking` |
| Amazon / AWS | `bedrock/moonshotai.kimi-k2.5` |
| Amazon / AWS | `bedrock/sa-east-1/deepseek.v3.2` |
| Amazon / AWS | `bedrock/sa-east-1/meta.llama3-70b-instruct-v1:0` |
| Amazon / AWS | `bedrock/sa-east-1/meta.llama3-8b-instruct-v1:0` |
| Amazon / AWS | `bedrock/sa-east-1/minimax.minimax-m2.1` |
| Amazon / AWS | `bedrock/sa-east-1/minimax.minimax-m2.5` |
| Amazon / AWS | `bedrock/sa-east-1/moonshotai.kimi-k2-thinking` |
| Amazon / AWS | `bedrock/sa-east-1/moonshotai.kimi-k2.5` |
| Amazon / AWS | `bedrock/sa-east-1/qwen.qwen3-coder-next` |
| Amazon / AWS | `bedrock/us-east-1/1-month-commitment/anthropic.claude-instant-v1` |
| Amazon / AWS | `bedrock/us-east-1/1-month-commitment/anthropic.claude-v1` |
| Amazon / AWS | `bedrock/us-east-1/1-month-commitment/anthropic.claude-v2:1` |
| Amazon / AWS | `bedrock/us-east-1/6-month-commitment/anthropic.claude-instant-v1` |
| Amazon / AWS | `bedrock/us-east-1/6-month-commitment/anthropic.claude-v1` |
| Amazon / AWS | `bedrock/us-east-1/6-month-commitment/anthropic.claude-v2:1` |
| Amazon / AWS | `bedrock/us-east-1/anthropic.claude-instant-v1` |
| Amazon / AWS | `bedrock/us-east-1/anthropic.claude-v1` |
| Amazon / AWS | `bedrock/us-east-1/anthropic.claude-v2:1` |
| Amazon / AWS | `bedrock/us-east-1/deepseek.v3.2` |
| Amazon / AWS | `bedrock/us-east-1/meta.llama3-70b-instruct-v1:0` |
| Amazon / AWS | `bedrock/us-east-1/meta.llama3-8b-instruct-v1:0` |
| Amazon / AWS | `bedrock/us-east-1/minimax.minimax-m2.1` |
| Amazon / AWS | `bedrock/us-east-1/minimax.minimax-m2.5` |
| Amazon / AWS | `bedrock/us-east-1/mistral.mistral-7b-instruct-v0:2` |
| Amazon / AWS | `bedrock/us-east-1/mistral.mistral-large-2402-v1:0` |
| Amazon / AWS | `bedrock/us-east-1/mistral.mixtral-8x7b-instruct-v0:1` |
| Amazon / AWS | `bedrock/us-east-1/moonshotai.kimi-k2-thinking` |
| Amazon / AWS | `bedrock/us-east-1/moonshotai.kimi-k2.5` |
| Amazon / AWS | `bedrock/us-east-1/qwen.qwen3-coder-next` |
| Amazon / AWS | `bedrock/us-east-1/zai.glm-5` |
| Amazon / AWS | `bedrock/us-east-2/deepseek.v3.2` |
| Amazon / AWS | `bedrock/us-east-2/minimax.minimax-m2.1` |
| Amazon / AWS | `bedrock/us-east-2/minimax.minimax-m2.5` |
| Amazon / AWS | `bedrock/us-east-2/moonshotai.kimi-k2-thinking` |
| Amazon / AWS | `bedrock/us-east-2/moonshotai.kimi-k2.5` |
| Amazon / AWS | `bedrock/us-east-2/qwen.qwen3-coder-next` |
| Amazon / AWS | `bedrock/us-gov-east-1/amazon.nova-pro-v1:0` |
| Amazon / AWS | `bedrock/us-gov-east-1/amazon.titan-embed-text-v1` |
| Amazon / AWS | `bedrock/us-gov-east-1/amazon.titan-embed-text-v2:0` |
| Amazon / AWS | `bedrock/us-gov-east-1/amazon.titan-text-express-v1` |
| Amazon / AWS | `bedrock/us-gov-east-1/amazon.titan-text-lite-v1` |
| Amazon / AWS | `bedrock/us-gov-east-1/amazon.titan-text-premier-v1:0` |
| Amazon / AWS | `bedrock/us-gov-east-1/anthropic.claude-3-5-sonnet-20240620-v1:0` |
| Amazon / AWS | `bedrock/us-gov-east-1/anthropic.claude-3-haiku-20240307-v1:0` |
| Amazon / AWS | `bedrock/us-gov-east-1/anthropic.claude-haiku-4-5-20251001-v1:0` |
| Amazon / AWS | `bedrock/us-gov-east-1/anthropic.claude-sonnet-4-5-20250929-v1:0` |
| Amazon / AWS | `bedrock/us-gov-east-1/claude-sonnet-4-5-20250929-v1:0` |
| Amazon / AWS | `bedrock/us-gov-east-1/meta.llama3-70b-instruct-v1:0` |
| Amazon / AWS | `bedrock/us-gov-east-1/meta.llama3-8b-instruct-v1:0` |
| Amazon / AWS | `bedrock/us-gov-west-1/amazon.nova-pro-v1:0` |
| Amazon / AWS | `bedrock/us-gov-west-1/amazon.titan-embed-text-v1` |
| Amazon / AWS | `bedrock/us-gov-west-1/amazon.titan-embed-text-v2:0` |
| Amazon / AWS | `bedrock/us-gov-west-1/amazon.titan-text-express-v1` |
| Amazon / AWS | `bedrock/us-gov-west-1/amazon.titan-text-lite-v1` |
| Amazon / AWS | `bedrock/us-gov-west-1/amazon.titan-text-premier-v1:0` |
| Amazon / AWS | `bedrock/us-gov-west-1/anthropic.claude-3-5-sonnet-20240620-v1:0` |
| Amazon / AWS | `bedrock/us-gov-west-1/anthropic.claude-3-7-sonnet-20250219-v1:0` |
| Amazon / AWS | `bedrock/us-gov-west-1/anthropic.claude-3-haiku-20240307-v1:0` |
| Amazon / AWS | `bedrock/us-gov-west-1/anthropic.claude-haiku-4-5-20251001-v1:0` |
| Amazon / AWS | `bedrock/us-gov-west-1/anthropic.claude-sonnet-4-5-20250929-v1:0` |
| Amazon / AWS | `bedrock/us-gov-west-1/claude-sonnet-4-5-20250929-v1:0` |
| Amazon / AWS | `bedrock/us-gov-west-1/meta.llama3-70b-instruct-v1:0` |
| Amazon / AWS | `bedrock/us-gov-west-1/meta.llama3-8b-instruct-v1:0` |
| Amazon / AWS | `bedrock/us-west-1/meta.llama3-70b-instruct-v1:0` |
| Amazon / AWS | `bedrock/us-west-1/meta.llama3-8b-instruct-v1:0` |
| Amazon / AWS | `bedrock/us-west-2/1-month-commitment/anthropic.claude-instant-v1` |
| Amazon / AWS | `bedrock/us-west-2/1-month-commitment/anthropic.claude-v1` |
| Amazon / AWS | `bedrock/us-west-2/1-month-commitment/anthropic.claude-v2:1` |
| Amazon / AWS | `bedrock/us-west-2/6-month-commitment/anthropic.claude-instant-v1` |
| Amazon / AWS | `bedrock/us-west-2/6-month-commitment/anthropic.claude-v1` |
| Amazon / AWS | `bedrock/us-west-2/6-month-commitment/anthropic.claude-v2:1` |
| Amazon / AWS | `bedrock/us-west-2/anthropic.claude-instant-v1` |
| Amazon / AWS | `bedrock/us-west-2/anthropic.claude-v1` |
| Amazon / AWS | `bedrock/us-west-2/anthropic.claude-v2:1` |
| Amazon / AWS | `bedrock/us-west-2/deepseek.v3.2` |
| Amazon / AWS | `bedrock/us-west-2/minimax.minimax-m2.1` |
| Amazon / AWS | `bedrock/us-west-2/minimax.minimax-m2.5` |
| Amazon / AWS | `bedrock/us-west-2/mistral.mistral-7b-instruct-v0:2` |
| Amazon / AWS | `bedrock/us-west-2/mistral.mistral-large-2402-v1:0` |
| Amazon / AWS | `bedrock/us-west-2/mistral.mixtral-8x7b-instruct-v0:1` |
| Amazon / AWS | `bedrock/us-west-2/moonshotai.kimi-k2-thinking` |
| Amazon / AWS | `bedrock/us-west-2/moonshotai.kimi-k2.5` |
| Amazon / AWS | `bedrock/us-west-2/qwen.qwen3-coder-next` |
| Amazon / AWS | `bedrock/us-west-2/zai.glm-5` |
| Amazon / AWS | `bedrock/us.anthropic.claude-3-5-haiku-20241022-v1:0` |
| Amazon / AWS | `claude-sonnet-4-5-20250929-v1:0` |
| Amazon / AWS | `cohere.command-light-text-v14` |
| Amazon / AWS | `cohere.command-r-plus-v1:0` |
| Amazon / AWS | `cohere.command-r-v1:0` |
| Amazon / AWS | `cohere.command-text-v14` |
| Amazon / AWS | `cohere.embed-english-v3` |
| Amazon / AWS | `cohere.embed-multilingual-v3` |
| Amazon / AWS | `cohere.embed-v4:0` |
| Amazon / AWS | `cohere.rerank-v3-5:0` |
| Amazon / AWS | `deepseek.r1-v1:0` |
| Amazon / AWS | `deepseek.v3-v1:0` |
| Amazon / AWS | `deepseek.v3.2` |
| Amazon / AWS | `eu.anthropic.claude-3-5-haiku-20241022-v1:0` |
| Amazon / AWS | `eu.anthropic.claude-3-5-sonnet-20240620-v1:0` |
| Amazon / AWS | `eu.anthropic.claude-3-5-sonnet-20241022-v2:0` |
| Amazon / AWS | `eu.anthropic.claude-3-7-sonnet-20250219-v1:0` |
| Amazon / AWS | `eu.anthropic.claude-3-haiku-20240307-v1:0` |
| Amazon / AWS | `eu.anthropic.claude-3-opus-20240229-v1:0` |
| Amazon / AWS | `eu.anthropic.claude-3-sonnet-20240229-v1:0` |
| Amazon / AWS | `eu.anthropic.claude-haiku-4-5-20251001-v1:0` |
| Amazon / AWS | `eu.anthropic.claude-opus-4-5-20251101-v1:0` |
| Amazon / AWS | `eu.anthropic.claude-opus-4-6-v1` |
| Amazon / AWS | `eu.anthropic.claude-opus-4-7` |
| Amazon / AWS | `eu.anthropic.claude-opus-4-8` |
| Amazon / AWS | `eu.anthropic.claude-sonnet-4-5-20250929-v1:0` |
| Amazon / AWS | `eu.anthropic.claude-sonnet-4-6` |
| Amazon / AWS | `eu.meta.llama3-2-1b-instruct-v1:0` |
| Amazon / AWS | `eu.meta.llama3-2-3b-instruct-v1:0` |
| Amazon / AWS | `eu.twelvelabs.marengo-embed-2-7-v1:0` |
| Amazon / AWS | `eu.twelvelabs.pegasus-1-2-v1:0` |
| Amazon / AWS | `global.anthropic.claude-haiku-4-5-20251001-v1:0` |
| Amazon / AWS | `global.anthropic.claude-opus-4-5-20251101-v1:0` |
| Amazon / AWS | `global.anthropic.claude-opus-4-6-v1` |
| Amazon / AWS | `global.anthropic.claude-opus-4-7` |
| Amazon / AWS | `global.anthropic.claude-opus-4-8` |
| Amazon / AWS | `global.anthropic.claude-sonnet-4-5-20250929-v1:0` |
| Amazon / AWS | `global.anthropic.claude-sonnet-4-6` |
| Amazon / AWS | `google.gemma-3-12b-it` |
| Amazon / AWS | `google.gemma-3-27b-it` |
| Amazon / AWS | `google.gemma-3-4b-it` |
| Amazon / AWS | `jp.anthropic.claude-opus-4-7` |
| Amazon / AWS | `jp.anthropic.claude-opus-4-8` |
| Amazon / AWS | `jp.anthropic.claude-sonnet-4-5-20250929-v1:0` |
| Amazon / AWS | `jp.anthropic.claude-sonnet-4-6` |
| Amazon / AWS | `max-x-max/50-steps/stability.stable-diffusion-xl-v0` |
| Amazon / AWS | `max-x-max/max-steps/stability.stable-diffusion-xl-v0` |
| Amazon / AWS | `meta.llama2-13b-chat-v1` |
| Amazon / AWS | `meta.llama2-70b-chat-v1` |
| Amazon / AWS | `meta.llama3-1-405b-instruct-v1:0` |
| Amazon / AWS | `meta.llama3-1-70b-instruct-v1:0` |
| Amazon / AWS | `meta.llama3-1-8b-instruct-v1:0` |
| Amazon / AWS | `meta.llama3-2-11b-instruct-v1:0` |
| Amazon / AWS | `meta.llama3-2-1b-instruct-v1:0` |
| Amazon / AWS | `meta.llama3-2-3b-instruct-v1:0` |
| Amazon / AWS | `meta.llama3-2-90b-instruct-v1:0` |
| Amazon / AWS | `meta.llama3-3-70b-instruct-v1:0` |
| Amazon / AWS | `meta.llama3-70b-instruct-v1:0` |
| Amazon / AWS | `meta.llama3-8b-instruct-v1:0` |
| Amazon / AWS | `meta.llama4-maverick-17b-instruct-v1:0` |
| Amazon / AWS | `meta.llama4-scout-17b-instruct-v1:0` |
| Amazon / AWS | `minimax.minimax-m2` |
| Amazon / AWS | `minimax.minimax-m2.1` |
| Amazon / AWS | `minimax.minimax-m2.5` |
| Amazon / AWS | `mistral.devstral-2-123b` |
| Amazon / AWS | `mistral.magistral-small-2509` |
| Amazon / AWS | `mistral.ministral-3-14b-instruct` |
| Amazon / AWS | `mistral.ministral-3-3b-instruct` |
| Amazon / AWS | `mistral.ministral-3-8b-instruct` |
| Amazon / AWS | `mistral.mistral-7b-instruct-v0:2` |
| Amazon / AWS | `mistral.mistral-large-2402-v1:0` |
| Amazon / AWS | `mistral.mistral-large-2407-v1:0` |
| Amazon / AWS | `mistral.mistral-large-3-675b-instruct` |
| Amazon / AWS | `mistral.mistral-small-2402-v1:0` |
| Amazon / AWS | `mistral.mixtral-8x7b-instruct-v0:1` |
| Amazon / AWS | `mistral.pixtral-large-2502-v1:0` |
| Amazon / AWS | `mistral.voxtral-mini-3b-2507` |
| Amazon / AWS | `mistral.voxtral-small-24b-2507` |
| Amazon / AWS | `moonshot.kimi-k2-thinking` |
| Amazon / AWS | `moonshotai.kimi-k2.5` |
| Amazon / AWS | `nvidia.nemotron-nano-12b-v2` |
| Amazon / AWS | `nvidia.nemotron-nano-3-30b` |
| Amazon / AWS | `nvidia.nemotron-nano-9b-v2` |
| Amazon / AWS | `nvidia.nemotron-super-3-120b` |
| Amazon / AWS | `openai.gpt-oss-120b-1:0` |
| Amazon / AWS | `openai.gpt-oss-20b-1:0` |
| Amazon / AWS | `openai.gpt-oss-safeguard-120b` |
| Amazon / AWS | `openai.gpt-oss-safeguard-20b` |
| Amazon / AWS | `qwen.qwen3-235b-a22b-2507-v1:0` |
| Amazon / AWS | `qwen.qwen3-32b-v1:0` |
| Amazon / AWS | `qwen.qwen3-coder-30b-a3b-v1:0` |
| Amazon / AWS | `qwen.qwen3-coder-480b-a35b-v1:0` |
| Amazon / AWS | `qwen.qwen3-coder-next` |
| Amazon / AWS | `qwen.qwen3-next-80b-a3b` |
| Amazon / AWS | `qwen.qwen3-vl-235b-a22b` |
| Amazon / AWS | `stability.sd3-5-large-v1:0` |
| Amazon / AWS | `stability.sd3-large-v1:0` |
| Amazon / AWS | `stability.stable-conservative-upscale-v1:0` |
| Amazon / AWS | `stability.stable-creative-upscale-v1:0` |
| Amazon / AWS | `stability.stable-fast-upscale-v1:0` |
| Amazon / AWS | `stability.stable-image-control-sketch-v1:0` |
| Amazon / AWS | `stability.stable-image-control-structure-v1:0` |
| Amazon / AWS | `stability.stable-image-core-v1:0` |
| Amazon / AWS | `stability.stable-image-core-v1:1` |
| Amazon / AWS | `stability.stable-image-erase-object-v1:0` |
| Amazon / AWS | `stability.stable-image-inpaint-v1:0` |
| Amazon / AWS | `stability.stable-image-remove-background-v1:0` |
| Amazon / AWS | `stability.stable-image-search-recolor-v1:0` |
| Amazon / AWS | `stability.stable-image-search-replace-v1:0` |
| Amazon / AWS | `stability.stable-image-style-guide-v1:0` |
| Amazon / AWS | `stability.stable-image-ultra-v1:0` |
| Amazon / AWS | `stability.stable-image-ultra-v1:1` |
| Amazon / AWS | `stability.stable-outpaint-v1:0` |
| Amazon / AWS | `stability.stable-style-transfer-v1:0` |
| Amazon / AWS | `twelvelabs.marengo-embed-2-7-v1:0` |
| Amazon / AWS | `twelvelabs.pegasus-1-2-v1:0` |
| Amazon / AWS | `us.amazon.nova-canvas-v1:0` |
| Amazon / AWS | `us.anthropic.claude-3-5-haiku-20241022-v1:0` |
| Amazon / AWS | `us.anthropic.claude-3-5-sonnet-20240620-v1:0` |
| Amazon / AWS | `us.anthropic.claude-3-5-sonnet-20241022-v2:0` |
| Amazon / AWS | `us.anthropic.claude-3-haiku-20240307-v1:0` |
| Amazon / AWS | `us.anthropic.claude-3-opus-20240229-v1:0` |
| Amazon / AWS | `us.anthropic.claude-3-sonnet-20240229-v1:0` |
| Amazon / AWS | `us.anthropic.claude-haiku-4-5-20251001-v1:0` |
| Amazon / AWS | `us.anthropic.claude-opus-4-1-20250805-v1:0` |
| Amazon / AWS | `us.anthropic.claude-opus-4-5-20251101-v1:0` |
| Amazon / AWS | `us.anthropic.claude-opus-4-6-v1` |
| Amazon / AWS | `us.anthropic.claude-opus-4-7` |
| Amazon / AWS | `us.anthropic.claude-opus-4-8` |
| Amazon / AWS | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` |
| Amazon / AWS | `us.anthropic.claude-sonnet-4-6` |
| Amazon / AWS | `us.deepseek.r1-v1:0` |
| Amazon / AWS | `us.meta.llama3-1-405b-instruct-v1:0` |
| Amazon / AWS | `us.meta.llama3-1-70b-instruct-v1:0` |
| Amazon / AWS | `us.meta.llama3-1-8b-instruct-v1:0` |
| Amazon / AWS | `us.meta.llama3-2-11b-instruct-v1:0` |
| Amazon / AWS | `us.meta.llama3-2-1b-instruct-v1:0` |
| Amazon / AWS | `us.meta.llama3-2-3b-instruct-v1:0` |
| Amazon / AWS | `us.meta.llama3-2-90b-instruct-v1:0` |
| Amazon / AWS | `us.meta.llama4-maverick-17b-instruct-v1:0` |
| Amazon / AWS | `us.meta.llama4-scout-17b-instruct-v1:0` |
| Amazon / AWS | `us.twelvelabs.marengo-embed-2-7-v1:0` |
| Amazon / AWS | `us.twelvelabs.pegasus-1-2-v1:0` |
| Amazon / AWS | `writer.palmyra-x4-v1:0` |
| Amazon / AWS | `writer.palmyra-x5-v1:0` |
| Amazon / AWS | `zai.glm-4.7` |
| Amazon / AWS | `zai.glm-4.7-flash` |
| Amazon / AWS | `zai.glm-5` |
| Ant Group | `Ling-1T` |
| Ant Group | `Ring-1T` |
| Anthropic | `claude-3-5-haiku-20241022` |
| Anthropic | `claude-3-5-haiku-latest` |
| Anthropic | `claude-3-5-sonnet-20240620` |
| Anthropic | `claude-3-5-sonnet-20241022` |
| Anthropic | `claude-3-7-sonnet-20250219` |
| Anthropic | `claude-3-haiku-20240307` |
| Anthropic | `claude-3-opus-20240229` |
| Anthropic | `claude-3-sonnet-20240229` |
| Anthropic | `claude-4-opus-20250514` |
| Anthropic | `claude-4-sonnet-20250514` |
| Anthropic | `claude-haiku-4-5` |
| Anthropic | `claude-haiku-4-5-20251001` |
| Anthropic | `claude-opus-4-0` |
| Anthropic | `claude-opus-4-1` |
| Anthropic | `claude-opus-4-1-20250805` |
| Anthropic | `claude-opus-4-20250514` |
| Anthropic | `claude-opus-4-5` |
| Anthropic | `claude-opus-4-5-20251101` |
| Anthropic | `claude-opus-4-6` |
| Anthropic | `claude-opus-4-6-20260205` |
| Anthropic | `claude-opus-4-7` |
| Anthropic | `claude-opus-4-7-20260416` |
| Anthropic | `claude-opus-4-8` |
| Anthropic | `claude-sonnet-4-0` |
| Anthropic | `claude-sonnet-4-20250514` |
| Anthropic | `claude-sonnet-4-5` |
| Anthropic | `claude-sonnet-4-5-20250929` |
| Anthropic | `claude-sonnet-4-6` |
| ByteDance / Seed | `deepseek-v3-2-251201` |
| ByteDance / Seed | `doubao-embedding` |
| ByteDance / Seed | `doubao-embedding-large` |
| ByteDance / Seed | `doubao-embedding-large-text-240915` |
| ByteDance / Seed | `doubao-embedding-large-text-250515` |
| ByteDance / Seed | `doubao-embedding-text-240715` |
| ByteDance / Seed | `glm-4-7-251222` |
| ByteDance / Seed | `kimi-k2-thinking-251104` |
| ByteDance / Seed | `volcengine/doubao-seed-2-0-code-preview-260215` |
| ByteDance / Seed | `volcengine/doubao-seed-2-0-lite-260215` |
| ByteDance / Seed | `volcengine/doubao-seed-2-0-mini-260215` |
| ByteDance / Seed | `volcengine/doubao-seed-2-0-pro-260215` |
| Cohere | `c4ai-aya-expanse-32b` |
| Cohere | `c4ai-aya-expanse-8b` |
| Cohere | `c4ai-aya-vision-32b` |
| Cohere | `c4ai-aya-vision-8b` |
| Cohere | `cohere/embed-v4.0` |
| Cohere | `command` |
| Cohere | `command-a-03-2025` |
| Cohere | `command-a-reasoning-08-2025` |
| Cohere | `command-a-translate-08-2025` |
| Cohere | `command-a-vision-07-2025` |
| Cohere | `command-nightly` |
| Cohere | `command-r-08-2024` |
| Cohere | `command-r-plus-08-2024` |
| Cohere | `command-r7b-12-2024` |
| Cohere | `command-r7b-arabic-02-2025` |
| Cohere | `embed-english-light-v2.0` |
| Cohere | `embed-english-light-v3.0` |
| Cohere | `embed-english-v2.0` |
| Cohere | `embed-english-v3.0` |
| Cohere | `embed-multilingual-light-v3.0` |
| Cohere | `embed-multilingual-v2.0` |
| Cohere | `embed-multilingual-v3.0` |
| Cohere | `rerank-english-v2.0` |
| Cohere | `rerank-english-v3.0` |
| Cohere | `rerank-multilingual-v2.0` |
| Cohere | `rerank-multilingual-v3.0` |
| Cohere | `rerank-v3.5` |
| Core42 / Inception / G42 | `mercury-2` |
| Core42 / Inception / G42 | `mercury-edit-2` |
| Databricks / MosaicML | `databricks-claude-haiku-4-5` |
| Databricks / MosaicML | `databricks-claude-opus-4-1` |
| Databricks / MosaicML | `databricks-claude-opus-4-5` |
| Databricks / MosaicML | `databricks-claude-opus-4-6` |
| Databricks / MosaicML | `databricks-claude-opus-4-7` |
| Databricks / MosaicML | `databricks-claude-sonnet-4` |
| Databricks / MosaicML | `databricks-claude-sonnet-4-5` |
| Databricks / MosaicML | `databricks-claude-sonnet-4-6` |
| Databricks / MosaicML | `databricks-gemini-2-5-flash` |
| Databricks / MosaicML | `databricks-gemini-2-5-pro` |
| Databricks / MosaicML | `databricks-gemini-3-1-flash-lite` |
| Databricks / MosaicML | `databricks-gemini-3-1-pro` |
| Databricks / MosaicML | `databricks-gemini-3-flash` |
| Databricks / MosaicML | `databricks-gemini-3-pro` |
| Databricks / MosaicML | `databricks-gpt-5` |
| Databricks / MosaicML | `databricks-gpt-5-1` |
| Databricks / MosaicML | `databricks-gpt-5-2` |
| Databricks / MosaicML | `databricks-gpt-5-4` |
| Databricks / MosaicML | `databricks-gpt-5-4-mini` |
| Databricks / MosaicML | `databricks-gpt-5-4-nano` |
| Databricks / MosaicML | `databricks-gpt-5-5` |
| Databricks / MosaicML | `databricks-gpt-5-mini` |
| Databricks / MosaicML | `databricks-gpt-5-nano` |
| Databricks / MosaicML | `databricks-gpt-oss-120b` |
| Databricks / MosaicML | `databricks-gpt-oss-20b` |
| Databricks / MosaicML | `databricks/databricks-bge-large-en` |
| Databricks / MosaicML | `databricks/databricks-claude-3-7-sonnet` |
| Databricks / MosaicML | `databricks/databricks-claude-haiku-4-5` |
| Databricks / MosaicML | `databricks/databricks-claude-opus-4` |
| Databricks / MosaicML | `databricks/databricks-claude-opus-4-1` |
| Databricks / MosaicML | `databricks/databricks-claude-opus-4-5` |
| Databricks / MosaicML | `databricks/databricks-claude-sonnet-4` |
| Databricks / MosaicML | `databricks/databricks-claude-sonnet-4-1` |
| Databricks / MosaicML | `databricks/databricks-claude-sonnet-4-5` |
| Databricks / MosaicML | `databricks/databricks-gemini-2-5-flash` |
| Databricks / MosaicML | `databricks/databricks-gemini-2-5-pro` |
| Databricks / MosaicML | `databricks/databricks-gemma-3-12b` |
| Databricks / MosaicML | `databricks/databricks-gpt-5` |
| Databricks / MosaicML | `databricks/databricks-gpt-5-1` |
| Databricks / MosaicML | `databricks/databricks-gpt-5-mini` |
| Databricks / MosaicML | `databricks/databricks-gpt-5-nano` |
| Databricks / MosaicML | `databricks/databricks-gpt-oss-120b` |
| Databricks / MosaicML | `databricks/databricks-gpt-oss-20b` |
| Databricks / MosaicML | `databricks/databricks-gte-large-en` |
| Databricks / MosaicML | `databricks/databricks-llama-2-70b-chat` |
| Databricks / MosaicML | `databricks/databricks-llama-4-maverick` |
| Databricks / MosaicML | `databricks/databricks-meta-llama-3-1-405b-instruct` |
| Databricks / MosaicML | `databricks/databricks-meta-llama-3-1-8b-instruct` |
| Databricks / MosaicML | `databricks/databricks-meta-llama-3-3-70b-instruct` |
| Databricks / MosaicML | `databricks/databricks-meta-llama-3-70b-instruct` |
| Databricks / MosaicML | `databricks/databricks-mixtral-8x7b-instruct` |
| Databricks / MosaicML | `databricks/databricks-mpt-30b-instruct` |
| Databricks / MosaicML | `databricks/databricks-mpt-7b-instruct` |
| DeepSeek | `deepseek-chat` |
| DeepSeek | `deepseek-reasoner` |
| DeepSeek | `deepseek-v4-flash` |
| DeepSeek | `deepseek-v4-pro` |
| DeepSeek | `deepseek/deepseek-chat` |
| DeepSeek | `deepseek/deepseek-coder` |
| DeepSeek | `deepseek/deepseek-r1` |
| DeepSeek | `deepseek/deepseek-reasoner` |
| DeepSeek | `deepseek/deepseek-v3` |
| DeepSeek | `deepseek/deepseek-v3.2` |
| Google / DeepMind | `gemini-2.0-flash` |
| Google / DeepMind | `gemini-2.0-flash-exp-image-generation` |
| Google / DeepMind | `gemini-2.0-flash-lite` |
| Google / DeepMind | `gemini-2.5-flash` |
| Google / DeepMind | `gemini-2.5-flash-image` |
| Google / DeepMind | `gemini-2.5-flash-lite` |
| Google / DeepMind | `gemini-2.5-flash-native-audio-latest` |
| Google / DeepMind | `gemini-2.5-flash-native-audio-preview-09-2025` |
| Google / DeepMind | `gemini-2.5-flash-native-audio-preview-12-2025` |
| Google / DeepMind | `gemini-2.5-flash-preview-tts` |
| Google / DeepMind | `gemini-2.5-pro` |
| Google / DeepMind | `gemini-2.5-pro-preview-tts` |
| Google / DeepMind | `gemini-3-flash-preview` |
| Google / DeepMind | `gemini-3-pro-preview` |
| Google / DeepMind | `gemini-3.1-flash-image-preview` |
| Google / DeepMind | `gemini-3.1-flash-lite` |
| Google / DeepMind | `gemini-3.1-flash-lite-preview` |
| Google / DeepMind | `gemini-3.1-flash-live-preview` |
| Google / DeepMind | `gemini-3.1-pro-preview` |
| Google / DeepMind | `gemini-3.1-pro-preview-customtools` |
| Google / DeepMind | `gemini-3.5-flash` |
| Google / DeepMind | `gemini-embedding-001` |
| Google / DeepMind | `gemini-exp-1206` |
| Google / DeepMind | `gemini-flash-latest` |
| Google / DeepMind | `gemini-flash-lite-latest` |
| Google / DeepMind | `gemini-pro-latest` |
| Google / DeepMind | `gemini/deep-research-pro-preview-12-2025` |
| Google / DeepMind | `gemini/gemini-1.5-flash` |
| Google / DeepMind | `gemini/gemini-2.0-flash` |
| Google / DeepMind | `gemini/gemini-2.0-flash-001` |
| Google / DeepMind | `gemini/gemini-2.0-flash-exp-image-generation` |
| Google / DeepMind | `gemini/gemini-2.0-flash-lite` |
| Google / DeepMind | `gemini/gemini-2.0-flash-lite-001` |
| Google / DeepMind | `gemini/gemini-2.5-computer-use-preview-10-2025` |
| Google / DeepMind | `gemini/gemini-2.5-flash` |
| Google / DeepMind | `gemini/gemini-2.5-flash-image` |
| Google / DeepMind | `gemini/gemini-2.5-flash-lite` |
| Google / DeepMind | `gemini/gemini-2.5-flash-lite-preview-06-17` |
| Google / DeepMind | `gemini/gemini-2.5-flash-lite-preview-09-2025` |
| Google / DeepMind | `gemini/gemini-2.5-flash-native-audio-latest` |
| Google / DeepMind | `gemini/gemini-2.5-flash-native-audio-preview-09-2025` |
| Google / DeepMind | `gemini/gemini-2.5-flash-native-audio-preview-12-2025` |
| Google / DeepMind | `gemini/gemini-2.5-flash-preview-09-2025` |
| Google / DeepMind | `gemini/gemini-2.5-flash-preview-tts` |
| Google / DeepMind | `gemini/gemini-2.5-pro` |
| Google / DeepMind | `gemini/gemini-2.5-pro-preview-tts` |
| Google / DeepMind | `gemini/gemini-3-flash-preview` |
| Google / DeepMind | `gemini/gemini-3-pro-image-preview` |
| Google / DeepMind | `gemini/gemini-3-pro-preview` |
| Google / DeepMind | `gemini/gemini-3.1-flash-image-preview` |
| Google / DeepMind | `gemini/gemini-3.1-flash-lite` |
| Google / DeepMind | `gemini/gemini-3.1-flash-lite-preview` |
| Google / DeepMind | `gemini/gemini-3.1-flash-live-preview` |
| Google / DeepMind | `gemini/gemini-3.1-pro-preview` |
| Google / DeepMind | `gemini/gemini-3.1-pro-preview-customtools` |
| Google / DeepMind | `gemini/gemini-3.5-flash` |
| Google / DeepMind | `gemini/gemini-embedding-001` |
| Google / DeepMind | `gemini/gemini-embedding-2` |
| Google / DeepMind | `gemini/gemini-embedding-2-preview` |
| Google / DeepMind | `gemini/gemini-exp-1114` |
| Google / DeepMind | `gemini/gemini-exp-1206` |
| Google / DeepMind | `gemini/gemini-flash-latest` |
| Google / DeepMind | `gemini/gemini-flash-lite-latest` |
| Google / DeepMind | `gemini/gemini-gemma-2-27b-it` |
| Google / DeepMind | `gemini/gemini-gemma-2-9b-it` |
| Google / DeepMind | `gemini/gemini-live-2.5-flash-preview-native-audio-09-2025` |
| Google / DeepMind | `gemini/gemini-pro-latest` |
| Google / DeepMind | `gemini/gemini-robotics-er-1.5-preview` |
| Google / DeepMind | `gemini/gemma-3-27b-it` |
| Google / DeepMind | `gemini/imagen-3.0-fast-generate-001` |
| Google / DeepMind | `gemini/imagen-3.0-generate-001` |
| Google / DeepMind | `gemini/imagen-3.0-generate-002` |
| Google / DeepMind | `gemini/imagen-4.0-fast-generate-001` |
| Google / DeepMind | `gemini/imagen-4.0-generate-001` |
| Google / DeepMind | `gemini/imagen-4.0-ultra-generate-001` |
| Google / DeepMind | `gemini/learnlm-1.5-pro-experimental` |
| Google / DeepMind | `gemini/lyria-3-clip-preview` |
| Google / DeepMind | `gemini/lyria-3-pro-preview` |
| Google / DeepMind | `gemini/veo-2.0-generate-001` |
| Google / DeepMind | `gemini/veo-3.1-fast-generate-001` |
| Google / DeepMind | `gemini/veo-3.1-fast-generate-preview` |
| Google / DeepMind | `gemini/veo-3.1-generate-001` |
| Google / DeepMind | `gemini/veo-3.1-generate-preview` |
| Google / DeepMind | `gemini/veo-3.1-lite-generate-preview` |
| Google / DeepMind | `gemma-3-27b-it` |
| Google / DeepMind | `gemma-4-26b-a4b-it` |
| Google / DeepMind | `gemma-4-31b-it` |
| Google / DeepMind | `vertex_ai/chirp` |
| Google / DeepMind | `vertex_ai/deepseek-ai/deepseek-ocr-maas` |
| Google / DeepMind | `vertex_ai/gemini-3-flash-preview` |
| Google / DeepMind | `vertex_ai/gemini-3-pro-preview` |
| Google / DeepMind | `vertex_ai/gemini-3.1-pro-preview` |
| Google / DeepMind | `vertex_ai/gemini-3.1-pro-preview-customtools` |
| Google / DeepMind | `vertex_ai/gemini-3.5-flash` |
| Google / DeepMind | `vertex_ai/gemini-embedding-2` |
| Google / DeepMind | `vertex_ai/gemini-embedding-2-preview` |
| Google / DeepMind | `vertex_ai/mistral-ocr-2505` |
| Google / DeepMind | `vertex_ai/search_api` |
| Google / DeepMind | `vertex_ai/xai/grok-4.1-fast-non-reasoning` |
| Google / DeepMind | `vertex_ai/xai/grok-4.1-fast-reasoning` |
| Google / DeepMind | `vertex_ai/xai/grok-4.20-non-reasoning` |
| Google / DeepMind | `vertex_ai/xai/grok-4.20-reasoning` |
| IBM | `watsonx/bigscience/mt0-xxl-13b` |
| IBM | `watsonx/core42/jais-13b-chat` |
| IBM | `watsonx/google/flan-t5-xl-3b` |
| IBM | `watsonx/ibm/granite-13b-chat-v2` |
| IBM | `watsonx/ibm/granite-13b-instruct-v2` |
| IBM | `watsonx/ibm/granite-3-3-8b-instruct` |
| IBM | `watsonx/ibm/granite-3-8b-instruct` |
| IBM | `watsonx/ibm/granite-4-h-small` |
| IBM | `watsonx/ibm/granite-guardian-3-2-2b` |
| IBM | `watsonx/ibm/granite-guardian-3-3-8b` |
| IBM | `watsonx/ibm/granite-ttm-1024-96-r2` |
| IBM | `watsonx/ibm/granite-ttm-1536-96-r2` |
| IBM | `watsonx/ibm/granite-ttm-512-96-r2` |
| IBM | `watsonx/ibm/granite-vision-3-2-2b` |
| IBM | `watsonx/meta-llama/llama-3-2-11b-vision-instruct` |
| IBM | `watsonx/meta-llama/llama-3-2-1b-instruct` |
| IBM | `watsonx/meta-llama/llama-3-2-3b-instruct` |
| IBM | `watsonx/meta-llama/llama-3-2-90b-vision-instruct` |
| IBM | `watsonx/meta-llama/llama-3-3-70b-instruct` |
| IBM | `watsonx/meta-llama/llama-4-maverick-17b` |
| IBM | `watsonx/meta-llama/llama-guard-3-11b-vision` |
| IBM | `watsonx/mistralai/mistral-large` |
| IBM | `watsonx/mistralai/mistral-medium-2505` |
| IBM | `watsonx/mistralai/mistral-small-2503` |
| IBM | `watsonx/mistralai/mistral-small-3-1-24b-instruct-2503` |
| IBM | `watsonx/mistralai/pixtral-12b-2409` |
| IBM | `watsonx/openai/gpt-oss-120b` |
| IBM | `watsonx/sdaia/allam-1-13b-instruct` |
| IBM | `watsonx/whisper-large-v3-turbo` |
| Meta AI | `meta_llama/Llama-3.3-70B-Instruct` |
| Meta AI | `meta_llama/Llama-3.3-8B-Instruct` |
| Meta AI | `meta_llama/Llama-4-Maverick-17B-128E-Instruct-FP8` |
| Meta AI | `meta_llama/Llama-4-Scout-17B-16E-Instruct-FP8` |
| Microsoft | `azure/ada` |
| Microsoft | `azure/codex-mini` |
| Microsoft | `azure/command-r-plus` |
| Microsoft | `azure/computer-use-preview` |
| Microsoft | `azure/container` |
| Microsoft | `azure/eu/gpt-4o-2024-08-06` |
| Microsoft | `azure/eu/gpt-4o-2024-11-20` |
| Microsoft | `azure/eu/gpt-4o-mini-2024-07-18` |
| Microsoft | `azure/eu/gpt-4o-mini-realtime-preview-2024-12-17` |
| Microsoft | `azure/eu/gpt-4o-realtime-preview-2024-10-01` |
| Microsoft | `azure/eu/gpt-4o-realtime-preview-2024-12-17` |
| Microsoft | `azure/eu/gpt-5-2025-08-07` |
| Microsoft | `azure/eu/gpt-5-mini-2025-08-07` |
| Microsoft | `azure/eu/gpt-5-nano-2025-08-07` |
| Microsoft | `azure/eu/gpt-5.1` |
| Microsoft | `azure/eu/gpt-5.1-chat` |
| Microsoft | `azure/eu/gpt-5.1-codex` |
| Microsoft | `azure/eu/gpt-5.1-codex-mini` |
| Microsoft | `azure/eu/o1-2024-12-17` |
| Microsoft | `azure/eu/o1-mini-2024-09-12` |
| Microsoft | `azure/eu/o1-preview-2024-09-12` |
| Microsoft | `azure/eu/o3-mini-2025-01-31` |
| Microsoft | `azure/global-standard/gpt-4o-2024-08-06` |
| Microsoft | `azure/global-standard/gpt-4o-2024-11-20` |
| Microsoft | `azure/global-standard/gpt-4o-mini` |
| Microsoft | `azure/global/gpt-4o-2024-08-06` |
| Microsoft | `azure/global/gpt-4o-2024-11-20` |
| Microsoft | `azure/global/gpt-5.1` |
| Microsoft | `azure/global/gpt-5.1-chat` |
| Microsoft | `azure/global/gpt-5.1-codex` |
| Microsoft | `azure/global/gpt-5.1-codex-mini` |
| Microsoft | `azure/gpt-3.5-turbo` |
| Microsoft | `azure/gpt-3.5-turbo-0125` |
| Microsoft | `azure/gpt-35-turbo` |
| Microsoft | `azure/gpt-35-turbo-0125` |
| Microsoft | `azure/gpt-35-turbo-1106` |
| Microsoft | `azure/gpt-35-turbo-16k` |
| Microsoft | `azure/gpt-35-turbo-16k-0613` |
| Microsoft | `azure/gpt-4` |
| Microsoft | `azure/gpt-4-0125-preview` |
| Microsoft | `azure/gpt-4-0613` |
| Microsoft | `azure/gpt-4-1106-preview` |
| Microsoft | `azure/gpt-4-32k` |
| Microsoft | `azure/gpt-4-32k-0613` |
| Microsoft | `azure/gpt-4-turbo` |
| Microsoft | `azure/gpt-4-turbo-2024-04-09` |
| Microsoft | `azure/gpt-4-turbo-vision-preview` |
| Microsoft | `azure/gpt-4.1` |
| Microsoft | `azure/gpt-4.1-2025-04-14` |
| Microsoft | `azure/gpt-4.1-mini` |
| Microsoft | `azure/gpt-4.1-mini-2025-04-14` |
| Microsoft | `azure/gpt-4.1-nano` |
| Microsoft | `azure/gpt-4.1-nano-2025-04-14` |
| Microsoft | `azure/gpt-4.5-preview` |
| Microsoft | `azure/gpt-4o` |
| Microsoft | `azure/gpt-4o-2024-05-13` |
| Microsoft | `azure/gpt-4o-2024-08-06` |
| Microsoft | `azure/gpt-4o-2024-11-20` |
| Microsoft | `azure/gpt-4o-audio-preview-2024-12-17` |
| Microsoft | `azure/gpt-4o-mini` |
| Microsoft | `azure/gpt-4o-mini-2024-07-18` |
| Microsoft | `azure/gpt-4o-mini-audio-preview-2024-12-17` |
| Microsoft | `azure/gpt-4o-mini-realtime-preview-2024-12-17` |
| Microsoft | `azure/gpt-4o-mini-transcribe` |
| Microsoft | `azure/gpt-4o-mini-tts` |
| Microsoft | `azure/gpt-4o-realtime-preview-2024-10-01` |
| Microsoft | `azure/gpt-4o-realtime-preview-2024-12-17` |
| Microsoft | `azure/gpt-4o-transcribe` |
| Microsoft | `azure/gpt-4o-transcribe-diarize` |
| Microsoft | `azure/gpt-5` |
| Microsoft | `azure/gpt-5-2025-08-07` |
| Microsoft | `azure/gpt-5-chat` |
| Microsoft | `azure/gpt-5-chat-latest` |
| Microsoft | `azure/gpt-5-codex` |
| Microsoft | `azure/gpt-5-mini` |
| Microsoft | `azure/gpt-5-mini-2025-08-07` |
| Microsoft | `azure/gpt-5-nano` |
| Microsoft | `azure/gpt-5-nano-2025-08-07` |
| Microsoft | `azure/gpt-5-pro` |
| Microsoft | `azure/gpt-5.1` |
| Microsoft | `azure/gpt-5.1-2025-11-13` |
| Microsoft | `azure/gpt-5.1-chat` |
| Microsoft | `azure/gpt-5.1-chat-2025-11-13` |
| Microsoft | `azure/gpt-5.1-codex` |
| Microsoft | `azure/gpt-5.1-codex-2025-11-13` |
| Microsoft | `azure/gpt-5.1-codex-max` |
| Microsoft | `azure/gpt-5.1-codex-mini` |
| Microsoft | `azure/gpt-5.1-codex-mini-2025-11-13` |
| Microsoft | `azure/gpt-5.2` |
| Microsoft | `azure/gpt-5.2-2025-12-11` |
| Microsoft | `azure/gpt-5.2-chat` |
| Microsoft | `azure/gpt-5.2-chat-2025-12-11` |
| Microsoft | `azure/gpt-5.2-codex` |
| Microsoft | `azure/gpt-5.2-pro` |
| Microsoft | `azure/gpt-5.2-pro-2025-12-11` |
| Microsoft | `azure/gpt-5.3-chat` |
| Microsoft | `azure/gpt-5.3-codex` |
| Microsoft | `azure/gpt-5.4` |
| Microsoft | `azure/gpt-5.4-2026-03-05` |
| Microsoft | `azure/gpt-5.4-mini` |
| Microsoft | `azure/gpt-5.4-mini-2026-03-17` |
| Microsoft | `azure/gpt-5.4-nano` |
| Microsoft | `azure/gpt-5.4-nano-2026-03-17` |
| Microsoft | `azure/gpt-5.4-pro` |
| Microsoft | `azure/gpt-5.4-pro-2026-03-05` |
| Microsoft | `azure/gpt-5.5` |
| Microsoft | `azure/gpt-5.5-2026-04-23` |
| Microsoft | `azure/gpt-5.5-pro` |
| Microsoft | `azure/gpt-5.5-pro-2026-04-23` |
| Microsoft | `azure/gpt-audio-1.5-2026-02-23` |
| Microsoft | `azure/gpt-audio-2025-08-28` |
| Microsoft | `azure/gpt-audio-mini-2025-10-06` |
| Microsoft | `azure/gpt-image-1` |
| Microsoft | `azure/gpt-image-1-mini` |
| Microsoft | `azure/gpt-image-1.5` |
| Microsoft | `azure/gpt-image-1.5-2025-12-16` |
| Microsoft | `azure/gpt-image-2` |
| Microsoft | `azure/gpt-image-2-2026-04-21` |
| Microsoft | `azure/gpt-realtime-1.5-2026-02-23` |
| Microsoft | `azure/gpt-realtime-2025-08-28` |
| Microsoft | `azure/gpt-realtime-mini-2025-10-06` |
| Microsoft | `azure/hd/1024-x-1024/dall-e-3` |
| Microsoft | `azure/hd/1024-x-1792/dall-e-3` |
| Microsoft | `azure/hd/1792-x-1024/dall-e-3` |
| Microsoft | `azure/high/1024-x-1024/gpt-image-1` |
| Microsoft | `azure/high/1024-x-1024/gpt-image-1-mini` |
| Microsoft | `azure/high/1024-x-1536/gpt-image-1` |
| Microsoft | `azure/high/1024-x-1536/gpt-image-1-mini` |
| Microsoft | `azure/high/1536-x-1024/gpt-image-1` |
| Microsoft | `azure/high/1536-x-1024/gpt-image-1-mini` |
| Microsoft | `azure/low/1024-x-1024/gpt-image-1` |
| Microsoft | `azure/low/1024-x-1024/gpt-image-1-mini` |
| Microsoft | `azure/low/1024-x-1536/gpt-image-1` |
| Microsoft | `azure/low/1024-x-1536/gpt-image-1-mini` |
| Microsoft | `azure/low/1536-x-1024/gpt-image-1` |
| Microsoft | `azure/low/1536-x-1024/gpt-image-1-mini` |
| Microsoft | `azure/medium/1024-x-1024/gpt-image-1` |
| Microsoft | `azure/medium/1024-x-1024/gpt-image-1-mini` |
| Microsoft | `azure/medium/1024-x-1536/gpt-image-1` |
| Microsoft | `azure/medium/1024-x-1536/gpt-image-1-mini` |
| Microsoft | `azure/medium/1536-x-1024/gpt-image-1` |
| Microsoft | `azure/medium/1536-x-1024/gpt-image-1-mini` |
| Microsoft | `azure/mistral-large-2402` |
| Microsoft | `azure/mistral-large-latest` |
| Microsoft | `azure/o1` |
| Microsoft | `azure/o1-2024-12-17` |
| Microsoft | `azure/o1-mini` |
| Microsoft | `azure/o1-mini-2024-09-12` |
| Microsoft | `azure/o1-preview` |
| Microsoft | `azure/o1-preview-2024-09-12` |
| Microsoft | `azure/o3` |
| Microsoft | `azure/o3-2025-04-16` |
| Microsoft | `azure/o3-deep-research` |
| Microsoft | `azure/o3-mini` |
| Microsoft | `azure/o3-mini-2025-01-31` |
| Microsoft | `azure/o3-pro` |
| Microsoft | `azure/o3-pro-2025-06-10` |
| Microsoft | `azure/o4-mini` |
| Microsoft | `azure/o4-mini-2025-04-16` |
| Microsoft | `azure/sora-2` |
| Microsoft | `azure/sora-2-pro` |
| Microsoft | `azure/sora-2-pro-high-res` |
| Microsoft | `azure/speech/azure-stt` |
| Microsoft | `azure/speech/azure-tts` |
| Microsoft | `azure/speech/azure-tts-hd` |
| Microsoft | `azure/standard/1024-x-1024/dall-e-2` |
| Microsoft | `azure/standard/1024-x-1024/dall-e-3` |
| Microsoft | `azure/standard/1024-x-1792/dall-e-3` |
| Microsoft | `azure/standard/1792-x-1024/dall-e-3` |
| Microsoft | `azure/text-embedding-3-large` |
| Microsoft | `azure/text-embedding-3-small` |
| Microsoft | `azure/text-embedding-ada-002` |
| Microsoft | `azure/tts-1` |
| Microsoft | `azure/tts-1-hd` |
| Microsoft | `azure/us/gpt-4.1-2025-04-14` |
| Microsoft | `azure/us/gpt-4.1-mini-2025-04-14` |
| Microsoft | `azure/us/gpt-4.1-nano-2025-04-14` |
| Microsoft | `azure/us/gpt-4o-2024-08-06` |
| Microsoft | `azure/us/gpt-4o-2024-11-20` |
| Microsoft | `azure/us/gpt-4o-mini-2024-07-18` |
| Microsoft | `azure/us/gpt-4o-mini-realtime-preview-2024-12-17` |
| Microsoft | `azure/us/gpt-4o-realtime-preview-2024-10-01` |
| Microsoft | `azure/us/gpt-4o-realtime-preview-2024-12-17` |
| Microsoft | `azure/us/gpt-5-2025-08-07` |
| Microsoft | `azure/us/gpt-5-mini-2025-08-07` |
| Microsoft | `azure/us/gpt-5-nano-2025-08-07` |
| Microsoft | `azure/us/gpt-5.1` |
| Microsoft | `azure/us/gpt-5.1-chat` |
| Microsoft | `azure/us/gpt-5.1-codex` |
| Microsoft | `azure/us/gpt-5.1-codex-mini` |
| Microsoft | `azure/us/o1-2024-12-17` |
| Microsoft | `azure/us/o1-mini-2024-09-12` |
| Microsoft | `azure/us/o1-preview-2024-09-12` |
| Microsoft | `azure/us/o3-2025-04-16` |
| Microsoft | `azure/us/o3-mini-2025-01-31` |
| Microsoft | `azure/us/o4-mini-2025-04-16` |
| Microsoft | `azure/whisper-1` |
| Microsoft | `azure_ai/Cohere-embed-v3-english` |
| Microsoft | `azure_ai/Cohere-embed-v3-multilingual` |
| Microsoft | `azure_ai/FLUX-1.1-pro` |
| Microsoft | `azure_ai/FLUX.1-Kontext-pro` |
| Microsoft | `azure_ai/Llama-3.2-11B-Vision-Instruct` |
| Microsoft | `azure_ai/Llama-3.2-90B-Vision-Instruct` |
| Microsoft | `azure_ai/Llama-3.3-70B-Instruct` |
| Microsoft | `azure_ai/Llama-4-Maverick-17B-128E-Instruct-FP8` |
| Microsoft | `azure_ai/Llama-4-Scout-17B-16E-Instruct` |
| Microsoft | `azure_ai/MAI-DS-R1` |
| Microsoft | `azure_ai/Meta-Llama-3-70B-Instruct` |
| Microsoft | `azure_ai/Meta-Llama-3.1-405B-Instruct` |
| Microsoft | `azure_ai/Meta-Llama-3.1-70B-Instruct` |
| Microsoft | `azure_ai/Meta-Llama-3.1-8B-Instruct` |
| Microsoft | `azure_ai/Phi-3-medium-128k-instruct` |
| Microsoft | `azure_ai/Phi-3-medium-4k-instruct` |
| Microsoft | `azure_ai/Phi-3-mini-128k-instruct` |
| Microsoft | `azure_ai/Phi-3-mini-4k-instruct` |
| Microsoft | `azure_ai/Phi-3-small-128k-instruct` |
| Microsoft | `azure_ai/Phi-3-small-8k-instruct` |
| Microsoft | `azure_ai/Phi-3.5-MoE-instruct` |
| Microsoft | `azure_ai/Phi-3.5-mini-instruct` |
| Microsoft | `azure_ai/Phi-3.5-vision-instruct` |
| Microsoft | `azure_ai/Phi-4` |
| Microsoft | `azure_ai/Phi-4-mini-instruct` |
| Microsoft | `azure_ai/Phi-4-mini-reasoning` |
| Microsoft | `azure_ai/Phi-4-multimodal-instruct` |
| Microsoft | `azure_ai/Phi-4-reasoning` |
| Microsoft | `azure_ai/claude-haiku-4-5` |
| Microsoft | `azure_ai/claude-opus-4-1` |
| Microsoft | `azure_ai/claude-opus-4-5` |
| Microsoft | `azure_ai/claude-opus-4-6` |
| Microsoft | `azure_ai/claude-opus-4-7` |
| Microsoft | `azure_ai/claude-opus-4-8` |
| Microsoft | `azure_ai/claude-sonnet-4-5` |
| Microsoft | `azure_ai/claude-sonnet-4-6` |
| Microsoft | `azure_ai/cohere-rerank-v3-english` |
| Microsoft | `azure_ai/cohere-rerank-v3-multilingual` |
| Microsoft | `azure_ai/cohere-rerank-v3.5` |
| Microsoft | `azure_ai/cohere-rerank-v4.0-fast` |
| Microsoft | `azure_ai/cohere-rerank-v4.0-pro` |
| Microsoft | `azure_ai/deepseek-r1` |
| Microsoft | `azure_ai/deepseek-v3` |
| Microsoft | `azure_ai/deepseek-v3-0324` |
| Microsoft | `azure_ai/deepseek-v3.2` |
| Microsoft | `azure_ai/deepseek-v3.2-speciale` |
| Microsoft | `azure_ai/doc-intelligence/prebuilt-document` |
| Microsoft | `azure_ai/doc-intelligence/prebuilt-layout` |
| Microsoft | `azure_ai/doc-intelligence/prebuilt-read` |
| Microsoft | `azure_ai/embed-v-4-0` |
| Microsoft | `azure_ai/flux.2-pro` |
| Microsoft | `azure_ai/global/grok-3` |
| Microsoft | `azure_ai/global/grok-3-mini` |
| Microsoft | `azure_ai/gpt-5.4` |
| Microsoft | `azure_ai/gpt-5.4-2026-03-05` |
| Microsoft | `azure_ai/gpt-5.4-mini` |
| Microsoft | `azure_ai/gpt-5.4-mini-2026-03-17` |
| Microsoft | `azure_ai/gpt-5.4-nano` |
| Microsoft | `azure_ai/gpt-5.4-nano-2026-03-17` |
| Microsoft | `azure_ai/gpt-5.4-pro` |
| Microsoft | `azure_ai/gpt-5.4-pro-2026-03-05` |
| Microsoft | `azure_ai/gpt-oss-120b` |
| Microsoft | `azure_ai/grok-3` |
| Microsoft | `azure_ai/grok-3-mini` |
| Microsoft | `azure_ai/grok-4` |
| Microsoft | `azure_ai/grok-4-1-fast-non-reasoning` |
| Microsoft | `azure_ai/grok-4-1-fast-reasoning` |
| Microsoft | `azure_ai/grok-4-fast-non-reasoning` |
| Microsoft | `azure_ai/grok-4-fast-reasoning` |
| Microsoft | `azure_ai/grok-code-fast-1` |
| Microsoft | `azure_ai/jais-30b-chat` |
| Microsoft | `azure_ai/jamba-instruct` |
| Microsoft | `azure_ai/kimi-k2.5` |
| Microsoft | `azure_ai/ministral-3b` |
| Microsoft | `azure_ai/mistral-document-ai-2505` |
| Microsoft | `azure_ai/mistral-document-ai-2512` |
| Microsoft | `azure_ai/mistral-large` |
| Microsoft | `azure_ai/mistral-large-2407` |
| Microsoft | `azure_ai/mistral-large-3` |
| Microsoft | `azure_ai/mistral-large-latest` |
| Microsoft | `azure_ai/mistral-medium-2505` |
| Microsoft | `azure_ai/mistral-nemo` |
| Microsoft | `azure_ai/mistral-small` |
| Microsoft | `azure_ai/mistral-small-2503` |
| Microsoft | `azure_ai/model_router` |
| Microsoft | `claude-haiku-4-5` |
| Microsoft | `claude-opus-4-1` |
| Microsoft | `claude-opus-4-5` |
| Microsoft | `claude-opus-4-6` |
| Microsoft | `claude-sonnet-4-5` |
| Microsoft | `claude-sonnet-4-6` |
| Microsoft | `codestral-2501` |
| Microsoft | `codex-mini` |
| Microsoft | `cohere-command-a` |
| Microsoft | `cohere-command-r-08-2024` |
| Microsoft | `cohere-command-r-plus-08-2024` |
| Microsoft | `cohere-embed-v-4-0` |
| Microsoft | `cohere-embed-v3-english` |
| Microsoft | `cohere-embed-v3-multilingual` |
| Microsoft | `computer-use-preview` |
| Microsoft | `deepseek-r1` |
| Microsoft | `deepseek-r1-0528` |
| Microsoft | `deepseek-v3-0324` |
| Microsoft | `deepseek-v3.1` |
| Microsoft | `deepseek-v3.2` |
| Microsoft | `deepseek-v3.2-speciale` |
| Microsoft | `gpt-3.5-turbo-0125` |
| Microsoft | `gpt-3.5-turbo-0301` |
| Microsoft | `gpt-3.5-turbo-0613` |
| Microsoft | `gpt-3.5-turbo-1106` |
| Microsoft | `gpt-3.5-turbo-instruct` |
| Microsoft | `gpt-4` |
| Microsoft | `gpt-4-32k` |
| Microsoft | `gpt-4-turbo` |
| Microsoft | `gpt-4-turbo-vision` |
| Microsoft | `gpt-4.1` |
| Microsoft | `gpt-4.1-mini` |
| Microsoft | `gpt-4.1-nano` |
| Microsoft | `gpt-4o` |
| Microsoft | `gpt-4o-mini` |
| Microsoft | `gpt-5` |
| Microsoft | `gpt-5-chat` |
| Microsoft | `gpt-5-codex` |
| Microsoft | `gpt-5-mini` |
| Microsoft | `gpt-5-nano` |
| Microsoft | `gpt-5-pro` |
| Microsoft | `gpt-5.1` |
| Microsoft | `gpt-5.1-chat` |
| Microsoft | `gpt-5.1-codex` |
| Microsoft | `gpt-5.1-codex-max` |
| Microsoft | `gpt-5.1-codex-mini` |
| Microsoft | `gpt-5.2` |
| Microsoft | `gpt-5.2-chat` |
| Microsoft | `gpt-5.2-codex` |
| Microsoft | `gpt-5.3-chat` |
| Microsoft | `gpt-5.3-codex` |
| Microsoft | `gpt-5.4` |
| Microsoft | `gpt-5.4-mini` |
| Microsoft | `gpt-5.4-nano` |
| Microsoft | `gpt-5.4-pro` |
| Microsoft | `gpt-5.5` |
| Microsoft | `grok-4-1-fast-non-reasoning` |
| Microsoft | `grok-4-1-fast-reasoning` |
| Microsoft | `grok-4-20-non-reasoning` |
| Microsoft | `grok-4-20-reasoning` |
| Microsoft | `grok-4-fast-reasoning` |
| Microsoft | `kimi-k2-thinking` |
| Microsoft | `kimi-k2.5` |
| Microsoft | `kimi-k2.6` |
| Microsoft | `llama-3.2-11b-vision-instruct` |
| Microsoft | `llama-3.2-90b-vision-instruct` |
| Microsoft | `llama-3.3-70b-instruct` |
| Microsoft | `llama-4-maverick-17b-128e-instruct-fp8` |
| Microsoft | `llama-4-scout-17b-16e-instruct` |
| Microsoft | `mai-ds-r1` |
| Microsoft | `meta-llama-3-70b-instruct` |
| Microsoft | `meta-llama-3-8b-instruct` |
| Microsoft | `meta-llama-3.1-405b-instruct` |
| Microsoft | `meta-llama-3.1-70b-instruct` |
| Microsoft | `meta-llama-3.1-8b-instruct` |
| Microsoft | `ministral-3b` |
| Microsoft | `mistral-large-2411` |
| Microsoft | `mistral-medium-2505` |
| Microsoft | `mistral-nemo` |
| Microsoft | `mistral-small-2503` |
| Microsoft | `model-router` |
| Microsoft | `o1` |
| Microsoft | `o1-mini` |
| Microsoft | `o1-preview` |
| Microsoft | `o3` |
| Microsoft | `o3-mini` |
| Microsoft | `o4-mini` |
| Microsoft | `phi-3-medium-128k-instruct` |
| Microsoft | `phi-3-medium-4k-instruct` |
| Microsoft | `phi-3-mini-128k-instruct` |
| Microsoft | `phi-3-mini-4k-instruct` |
| Microsoft | `phi-3-small-128k-instruct` |
| Microsoft | `phi-3-small-8k-instruct` |
| Microsoft | `phi-3.5-mini-instruct` |
| Microsoft | `phi-3.5-moe-instruct` |
| Microsoft | `phi-4` |
| Microsoft | `phi-4-mini` |
| Microsoft | `phi-4-mini-reasoning` |
| Microsoft | `phi-4-multimodal` |
| Microsoft | `phi-4-reasoning` |
| Microsoft | `phi-4-reasoning-plus` |
| Microsoft | `text-embedding-3-large` |
| Microsoft | `text-embedding-3-small` |
| Microsoft | `text-embedding-ada-002` |
| MiniMax | `MiniMax-M2` |
| MiniMax | `MiniMax-M2.1` |
| MiniMax | `MiniMax-M2.5` |
| MiniMax | `MiniMax-M2.5-highspeed` |
| MiniMax | `MiniMax-M2.7` |
| MiniMax | `MiniMax-M2.7-highspeed` |
| MiniMax | `MiniMax-M3` |
| MiniMax | `minimax/MiniMax-M2` |
| MiniMax | `minimax/MiniMax-M2.1` |
| MiniMax | `minimax/MiniMax-M2.1-lightning` |
| MiniMax | `minimax/MiniMax-M2.5` |
| MiniMax | `minimax/MiniMax-M2.5-lightning` |
| MiniMax | `minimax/speech-02-hd` |
| MiniMax | `minimax/speech-02-turbo` |
| MiniMax | `minimax/speech-2.6-hd` |
| MiniMax | `minimax/speech-2.6-turbo` |
| Mistral AI | `codestral-latest` |
| Mistral AI | `devstral-2512` |
| Mistral AI | `devstral-latest` |
| Mistral AI | `devstral-medium-2507` |
| Mistral AI | `devstral-medium-latest` |
| Mistral AI | `devstral-small-2505` |
| Mistral AI | `devstral-small-2507` |
| Mistral AI | `labs-devstral-small-2512` |
| Mistral AI | `magistral-medium-latest` |
| Mistral AI | `magistral-small` |
| Mistral AI | `ministral-3b-latest` |
| Mistral AI | `ministral-8b-latest` |
| Mistral AI | `mistral-embed` |
| Mistral AI | `mistral-large-2411` |
| Mistral AI | `mistral-large-2512` |
| Mistral AI | `mistral-large-latest` |
| Mistral AI | `mistral-medium-2505` |
| Mistral AI | `mistral-medium-2508` |
| Mistral AI | `mistral-medium-2604` |
| Mistral AI | `mistral-medium-latest` |
| Mistral AI | `mistral-nemo` |
| Mistral AI | `mistral-small-2506` |
| Mistral AI | `mistral-small-2603` |
| Mistral AI | `mistral-small-latest` |
| Mistral AI | `mistral/codestral-2405` |
| Mistral AI | `mistral/codestral-2508` |
| Mistral AI | `mistral/codestral-embed` |
| Mistral AI | `mistral/codestral-embed-2505` |
| Mistral AI | `mistral/codestral-latest` |
| Mistral AI | `mistral/codestral-mamba-latest` |
| Mistral AI | `mistral/devstral-2512` |
| Mistral AI | `mistral/devstral-latest` |
| Mistral AI | `mistral/devstral-medium-2507` |
| Mistral AI | `mistral/devstral-medium-latest` |
| Mistral AI | `mistral/devstral-small-2505` |
| Mistral AI | `mistral/devstral-small-2507` |
| Mistral AI | `mistral/devstral-small-latest` |
| Mistral AI | `mistral/labs-devstral-small-2512` |
| Mistral AI | `mistral/magistral-medium-1-2-2509` |
| Mistral AI | `mistral/magistral-medium-2506` |
| Mistral AI | `mistral/magistral-medium-2509` |
| Mistral AI | `mistral/magistral-medium-latest` |
| Mistral AI | `mistral/magistral-small-1-2-2509` |
| Mistral AI | `mistral/magistral-small-2506` |
| Mistral AI | `mistral/magistral-small-latest` |
| Mistral AI | `mistral/ministral-3-14b-2512` |
| Mistral AI | `mistral/ministral-3-3b-2512` |
| Mistral AI | `mistral/ministral-3-8b-2512` |
| Mistral AI | `mistral/ministral-8b-2512` |
| Mistral AI | `mistral/mistral-embed` |
| Mistral AI | `mistral/mistral-large-2402` |
| Mistral AI | `mistral/mistral-large-2407` |
| Mistral AI | `mistral/mistral-large-2411` |
| Mistral AI | `mistral/mistral-large-2512` |
| Mistral AI | `mistral/mistral-large-3` |
| Mistral AI | `mistral/mistral-large-latest` |
| Mistral AI | `mistral/mistral-medium` |
| Mistral AI | `mistral/mistral-medium-2312` |
| Mistral AI | `mistral/mistral-medium-2505` |
| Mistral AI | `mistral/mistral-medium-3-1-2508` |
| Mistral AI | `mistral/mistral-medium-latest` |
| Mistral AI | `mistral/mistral-ocr-2505-completion` |
| Mistral AI | `mistral/mistral-ocr-latest` |
| Mistral AI | `mistral/mistral-small` |
| Mistral AI | `mistral/mistral-small-3-2-2506` |
| Mistral AI | `mistral/mistral-small-latest` |
| Mistral AI | `mistral/mistral-tiny` |
| Mistral AI | `mistral/open-codestral-mamba` |
| Mistral AI | `mistral/open-mistral-7b` |
| Mistral AI | `mistral/open-mistral-nemo` |
| Mistral AI | `mistral/open-mistral-nemo-2407` |
| Mistral AI | `mistral/open-mixtral-8x22b` |
| Mistral AI | `mistral/open-mixtral-8x7b` |
| Mistral AI | `mistral/pixtral-12b-2409` |
| Mistral AI | `mistral/pixtral-large-2411` |
| Mistral AI | `mistral/pixtral-large-latest` |
| Mistral AI | `open-mistral-7b` |
| Mistral AI | `open-mistral-nemo` |
| Mistral AI | `open-mixtral-8x22b` |
| Mistral AI | `open-mixtral-8x7b` |
| Mistral AI | `pixtral-12b` |
| Mistral AI | `pixtral-large-latest` |
| Moonshot AI | `kimi-k2-0711-preview` |
| Moonshot AI | `kimi-k2-0905-preview` |
| Moonshot AI | `kimi-k2-thinking` |
| Moonshot AI | `kimi-k2-thinking-turbo` |
| Moonshot AI | `kimi-k2-turbo-preview` |
| Moonshot AI | `kimi-k2.5` |
| Moonshot AI | `kimi-k2.6` |
| Moonshot AI | `moonshot/kimi-k2-0711-preview` |
| Moonshot AI | `moonshot/kimi-k2-0905-preview` |
| Moonshot AI | `moonshot/kimi-k2-thinking` |
| Moonshot AI | `moonshot/kimi-k2-thinking-turbo` |
| Moonshot AI | `moonshot/kimi-k2-turbo-preview` |
| Moonshot AI | `moonshot/kimi-k2.5` |
| Moonshot AI | `moonshot/kimi-k2.6` |
| Moonshot AI | `moonshot/kimi-latest` |
| Moonshot AI | `moonshot/kimi-latest-128k` |
| Moonshot AI | `moonshot/kimi-latest-32k` |
| Moonshot AI | `moonshot/kimi-latest-8k` |
| Moonshot AI | `moonshot/kimi-thinking-preview` |
| Moonshot AI | `moonshot/moonshot-v1-128k` |
| Moonshot AI | `moonshot/moonshot-v1-128k-0430` |
| Moonshot AI | `moonshot/moonshot-v1-128k-vision-preview` |
| Moonshot AI | `moonshot/moonshot-v1-32k` |
| Moonshot AI | `moonshot/moonshot-v1-32k-0430` |
| Moonshot AI | `moonshot/moonshot-v1-32k-vision-preview` |
| Moonshot AI | `moonshot/moonshot-v1-8k` |
| Moonshot AI | `moonshot/moonshot-v1-8k-0430` |
| Moonshot AI | `moonshot/moonshot-v1-8k-vision-preview` |
| Moonshot AI | `moonshot/moonshot-v1-auto` |
| Morph | `auto` |
| Morph | `morph-v3-fast` |
| Morph | `morph-v3-large` |
| Morph | `morph/morph-v3-fast` |
| Morph | `morph/morph-v3-large` |
| NVIDIA | `abacusai/dracarys-llama-3_1-70b-instruct` |
| NVIDIA | `baai/bge-m3` |
| NVIDIA | `black-forest-labs/flux.1-dev` |
| NVIDIA | `black-forest-labs/flux_1-kontext-dev` |
| NVIDIA | `black-forest-labs/flux_1-schnell` |
| NVIDIA | `black-forest-labs/flux_2-klein-4b` |
| NVIDIA | `bytedance/seed-oss-36b-instruct` |
| NVIDIA | `deepseek-ai/deepseek-v3.1-terminus` |
| NVIDIA | `deepseek-ai/deepseek-v3.2` |
| NVIDIA | `deepseek-ai/deepseek-v4-flash` |
| NVIDIA | `deepseek-ai/deepseek-v4-pro` |
| NVIDIA | `google/gemma-2-2b-it` |
| NVIDIA | `google/gemma-3-27b-it` |
| NVIDIA | `google/gemma-3n-e2b-it` |
| NVIDIA | `google/gemma-3n-e4b-it` |
| NVIDIA | `google/gemma-4-31b-it` |
| NVIDIA | `google/google-paligemma` |
| NVIDIA | `meta/esm2-650m` |
| NVIDIA | `meta/esmfold` |
| NVIDIA | `meta/llama-3.1-70b-instruct` |
| NVIDIA | `meta/llama-3.1-8b-instruct` |
| NVIDIA | `meta/llama-3.2-11b-vision-instruct` |
| NVIDIA | `meta/llama-3.2-1b-instruct` |
| NVIDIA | `meta/llama-3.2-3b-instruct` |
| NVIDIA | `meta/llama-3.2-90b-vision-instruct` |
| NVIDIA | `meta/llama-3.3-70b-instruct` |
| NVIDIA | `meta/llama-4-maverick-17b-128e-instruct` |
| NVIDIA | `meta/llama-guard-4-12b` |
| NVIDIA | `microsoft/phi-4-mini-instruct` |
| NVIDIA | `microsoft/phi-4-multimodal-instruct` |
| NVIDIA | `minimaxai/minimax-m2.5` |
| NVIDIA | `minimaxai/minimax-m2.7` |
| NVIDIA | `mistralai/devstral-2-123b-instruct-2512` |
| NVIDIA | `mistralai/magistral-small-2506` |
| NVIDIA | `mistralai/mistral-7b-instruct-v03` |
| NVIDIA | `mistralai/mistral-large-3-675b-instruct-2512` |
| NVIDIA | `mistralai/mistral-medium-3-instruct` |
| NVIDIA | `mistralai/mistral-nemotron` |
| NVIDIA | `mistralai/mistral-small-4-119b-2603` |
| NVIDIA | `mistralai/mixtral-8x22b-instruct` |
| NVIDIA | `mistralai/mixtral-8x7b-instruct` |
| NVIDIA | `moonshotai/kimi-k2-instruct` |
| NVIDIA | `moonshotai/kimi-k2-instruct-0905` |
| NVIDIA | `moonshotai/kimi-k2-thinking` |
| NVIDIA | `moonshotai/kimi-k2.6` |
| NVIDIA | `nvidia/active-speaker-detection` |
| NVIDIA | `nvidia/bevformer` |
| NVIDIA | `nvidia/cosmos-predict1-5b` |
| NVIDIA | `nvidia/cosmos-transfer1-7b` |
| NVIDIA | `nvidia/cosmos-transfer2_5-2b` |
| NVIDIA | `nvidia/gliner-pii` |
| NVIDIA | `nvidia/llama-3_1-nemotron-safety-guard-8b-v3` |
| NVIDIA | `nvidia/llama-3_2-nemoretriever-300m-embed-v1` |
| NVIDIA | `nvidia/llama-3_3-nemotron-super-49b-v1` |
| NVIDIA | `nvidia/llama-3_3-nemotron-super-49b-v1_5` |
| NVIDIA | `nvidia/llama-nemotron-embed-vl-1b-v2` |
| NVIDIA | `nvidia/llama-nemotron-rerank-vl-1b-v2` |
| NVIDIA | `nvidia/magpie-tts-zeroshot` |
| NVIDIA | `nvidia/nemotron-3-content-safety` |
| NVIDIA | `nvidia/nemotron-3-nano-30b-a3b` |
| NVIDIA | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` |
| NVIDIA | `nvidia/nemotron-3-super-120b-a12b` |
| NVIDIA | `nvidia/nemotron-content-safety-reasoning-4b` |
| NVIDIA | `nvidia/nemotron-mini-4b-instruct` |
| NVIDIA | `nvidia/nemotron-voicechat` |
| NVIDIA | `nvidia/nv-embed-v1` |
| NVIDIA | `nvidia/nv-embedcode-7b-v1` |
| NVIDIA | `nvidia/nvidia-nemotron-nano-9b-v2` |
| NVIDIA | `nvidia/rerank-qa-mistral-4b` |
| NVIDIA | `nvidia/riva-translate-4b-instruct-v1_1` |
| NVIDIA | `nvidia/sparsedrive` |
| NVIDIA | `nvidia/streampetr` |
| NVIDIA | `nvidia/studiovoice` |
| NVIDIA | `nvidia/synthetic-video-detector` |
| NVIDIA | `nvidia/usdcode` |
| NVIDIA | `nvidia/usdvalidate` |
| NVIDIA | `openai/gpt-oss-120b` |
| NVIDIA | `openai/gpt-oss-20b` |
| NVIDIA | `openai/whisper-large-v3` |
| NVIDIA | `qwen/qwen-image` |
| NVIDIA | `qwen/qwen-image-edit` |
| NVIDIA | `qwen/qwen2.5-coder-32b-instruct` |
| NVIDIA | `qwen/qwen3-coder-480b-a35b-instruct` |
| NVIDIA | `qwen/qwen3-next-80b-a3b-instruct` |
| NVIDIA | `qwen/qwen3-next-80b-a3b-thinking` |
| NVIDIA | `qwen/qwen3.5-122b-a10b` |
| NVIDIA | `qwen/qwen3.5-397b-a17b` |
| NVIDIA | `sarvamai/sarvam-m` |
| NVIDIA | `stepfun-ai/step-3.5-flash` |
| NVIDIA | `stepfun-ai/step-3.7-flash` |
| NVIDIA | `upstage/solar-10_7b-instruct` |
| NVIDIA | `z-ai/glm-5.1` |
| NVIDIA | `z-ai/glm4.7` |
| OpenAI | `1024-x-1024/dall-e-2` |
| OpenAI | `1024-x-1024/gpt-image-1.5` |
| OpenAI | `1024-x-1024/gpt-image-1.5-2025-12-16` |
| OpenAI | `1024-x-1536/gpt-image-1.5` |
| OpenAI | `1024-x-1536/gpt-image-1.5-2025-12-16` |
| OpenAI | `1536-x-1024/gpt-image-1.5` |
| OpenAI | `1536-x-1024/gpt-image-1.5-2025-12-16` |
| OpenAI | `256-x-256/dall-e-2` |
| OpenAI | `512-x-512/dall-e-2` |
| OpenAI | `chatgpt-4o-latest` |
| OpenAI | `chatgpt-image-latest` |
| OpenAI | `codex-mini-latest` |
| OpenAI | `dall-e-2` |
| OpenAI | `dall-e-3` |
| OpenAI | `ft:gpt-3.5-turbo` |
| OpenAI | `ft:gpt-3.5-turbo-0125` |
| OpenAI | `ft:gpt-3.5-turbo-0613` |
| OpenAI | `ft:gpt-3.5-turbo-1106` |
| OpenAI | `ft:gpt-4-0613` |
| OpenAI | `ft:gpt-4.1-2025-04-14` |
| OpenAI | `ft:gpt-4.1-mini-2025-04-14` |
| OpenAI | `ft:gpt-4.1-nano-2025-04-14` |
| OpenAI | `ft:gpt-4o-2024-08-06` |
| OpenAI | `ft:gpt-4o-2024-11-20` |
| OpenAI | `ft:gpt-4o-mini-2024-07-18` |
| OpenAI | `ft:o4-mini-2025-04-16` |
| OpenAI | `gpt-3.5-turbo` |
| OpenAI | `gpt-3.5-turbo-0125` |
| OpenAI | `gpt-3.5-turbo-1106` |
| OpenAI | `gpt-3.5-turbo-16k` |
| OpenAI | `gpt-4` |
| OpenAI | `gpt-4-0125-preview` |
| OpenAI | `gpt-4-0314` |
| OpenAI | `gpt-4-0613` |
| OpenAI | `gpt-4-1106-preview` |
| OpenAI | `gpt-4-turbo` |
| OpenAI | `gpt-4-turbo-2024-04-09` |
| OpenAI | `gpt-4-turbo-preview` |
| OpenAI | `gpt-4.1` |
| OpenAI | `gpt-4.1-2025-04-14` |
| OpenAI | `gpt-4.1-mini` |
| OpenAI | `gpt-4.1-mini-2025-04-14` |
| OpenAI | `gpt-4.1-nano` |
| OpenAI | `gpt-4.1-nano-2025-04-14` |
| OpenAI | `gpt-4o` |
| OpenAI | `gpt-4o-2024-05-13` |
| OpenAI | `gpt-4o-2024-08-06` |
| OpenAI | `gpt-4o-2024-11-20` |
| OpenAI | `gpt-4o-audio-preview` |
| OpenAI | `gpt-4o-audio-preview-2024-12-17` |
| OpenAI | `gpt-4o-audio-preview-2025-06-03` |
| OpenAI | `gpt-4o-mini` |
| OpenAI | `gpt-4o-mini-2024-07-18` |
| OpenAI | `gpt-4o-mini-audio-preview` |
| OpenAI | `gpt-4o-mini-audio-preview-2024-12-17` |
| OpenAI | `gpt-4o-mini-realtime-preview` |
| OpenAI | `gpt-4o-mini-realtime-preview-2024-12-17` |
| OpenAI | `gpt-4o-mini-search-preview` |
| OpenAI | `gpt-4o-mini-search-preview-2025-03-11` |
| OpenAI | `gpt-4o-mini-transcribe` |
| OpenAI | `gpt-4o-mini-transcribe-2025-03-20` |
| OpenAI | `gpt-4o-mini-transcribe-2025-12-15` |
| OpenAI | `gpt-4o-mini-tts` |
| OpenAI | `gpt-4o-mini-tts-2025-03-20` |
| OpenAI | `gpt-4o-mini-tts-2025-12-15` |
| OpenAI | `gpt-4o-realtime-preview` |
| OpenAI | `gpt-4o-realtime-preview-2024-12-17` |
| OpenAI | `gpt-4o-realtime-preview-2025-06-03` |
| OpenAI | `gpt-4o-search-preview` |
| OpenAI | `gpt-4o-search-preview-2025-03-11` |
| OpenAI | `gpt-4o-transcribe` |
| OpenAI | `gpt-4o-transcribe-diarize` |
| OpenAI | `gpt-5` |
| OpenAI | `gpt-5-2025-08-07` |
| OpenAI | `gpt-5-chat` |
| OpenAI | `gpt-5-chat-latest` |
| OpenAI | `gpt-5-codex` |
| OpenAI | `gpt-5-mini` |
| OpenAI | `gpt-5-mini-2025-08-07` |
| OpenAI | `gpt-5-nano` |
| OpenAI | `gpt-5-nano-2025-08-07` |
| OpenAI | `gpt-5-pro` |
| OpenAI | `gpt-5-pro-2025-10-06` |
| OpenAI | `gpt-5-search-api` |
| OpenAI | `gpt-5-search-api-2025-10-14` |
| OpenAI | `gpt-5.1` |
| OpenAI | `gpt-5.1-2025-11-13` |
| OpenAI | `gpt-5.1-chat-latest` |
| OpenAI | `gpt-5.1-codex` |
| OpenAI | `gpt-5.1-codex-max` |
| OpenAI | `gpt-5.1-codex-mini` |
| OpenAI | `gpt-5.2` |
| OpenAI | `gpt-5.2-2025-12-11` |
| OpenAI | `gpt-5.2-chat-latest` |
| OpenAI | `gpt-5.2-codex` |
| OpenAI | `gpt-5.2-pro` |
| OpenAI | `gpt-5.2-pro-2025-12-11` |
| OpenAI | `gpt-5.3-chat-latest` |
| OpenAI | `gpt-5.3-codex` |
| OpenAI | `gpt-5.3-codex-spark` |
| OpenAI | `gpt-5.4` |
| OpenAI | `gpt-5.4-2026-03-05` |
| OpenAI | `gpt-5.4-mini` |
| OpenAI | `gpt-5.4-mini-2026-03-17` |
| OpenAI | `gpt-5.4-nano` |
| OpenAI | `gpt-5.4-nano-2026-03-17` |
| OpenAI | `gpt-5.4-pro` |
| OpenAI | `gpt-5.4-pro-2026-03-05` |
| OpenAI | `gpt-5.5` |
| OpenAI | `gpt-5.5-2026-04-23` |
| OpenAI | `gpt-5.5-pro` |
| OpenAI | `gpt-5.5-pro-2026-04-23` |
| OpenAI | `gpt-audio` |
| OpenAI | `gpt-audio-1.5` |
| OpenAI | `gpt-audio-2025-08-28` |
| OpenAI | `gpt-audio-mini` |
| OpenAI | `gpt-audio-mini-2025-10-06` |
| OpenAI | `gpt-audio-mini-2025-12-15` |
| OpenAI | `gpt-image-1` |
| OpenAI | `gpt-image-1-mini` |
| OpenAI | `gpt-image-1.5` |
| OpenAI | `gpt-image-1.5-2025-12-16` |
| OpenAI | `gpt-image-2` |
| OpenAI | `gpt-image-2-2026-04-21` |
| OpenAI | `gpt-realtime` |
| OpenAI | `gpt-realtime-1.5` |
| OpenAI | `gpt-realtime-2` |
| OpenAI | `gpt-realtime-2025-08-28` |
| OpenAI | `gpt-realtime-mini` |
| OpenAI | `gpt-realtime-mini-2025-10-06` |
| OpenAI | `gpt-realtime-mini-2025-12-15` |
| OpenAI | `hd/1024-x-1024/dall-e-3` |
| OpenAI | `hd/1024-x-1792/dall-e-3` |
| OpenAI | `hd/1792-x-1024/dall-e-3` |
| OpenAI | `high/1024-x-1024/gpt-image-1` |
| OpenAI | `high/1024-x-1024/gpt-image-1.5` |
| OpenAI | `high/1024-x-1024/gpt-image-1.5-2025-12-16` |
| OpenAI | `high/1024-x-1536/gpt-image-1` |
| OpenAI | `high/1024-x-1536/gpt-image-1.5` |
| OpenAI | `high/1024-x-1536/gpt-image-1.5-2025-12-16` |
| OpenAI | `high/1536-x-1024/gpt-image-1` |
| OpenAI | `high/1536-x-1024/gpt-image-1.5` |
| OpenAI | `high/1536-x-1024/gpt-image-1.5-2025-12-16` |
| OpenAI | `low/1024-x-1024/gpt-image-1` |
| OpenAI | `low/1024-x-1024/gpt-image-1-mini` |
| OpenAI | `low/1024-x-1024/gpt-image-1.5` |
| OpenAI | `low/1024-x-1024/gpt-image-1.5-2025-12-16` |
| OpenAI | `low/1024-x-1536/gpt-image-1` |
| OpenAI | `low/1024-x-1536/gpt-image-1-mini` |
| OpenAI | `low/1024-x-1536/gpt-image-1.5` |
| OpenAI | `low/1024-x-1536/gpt-image-1.5-2025-12-16` |
| OpenAI | `low/1536-x-1024/gpt-image-1` |
| OpenAI | `low/1536-x-1024/gpt-image-1-mini` |
| OpenAI | `low/1536-x-1024/gpt-image-1.5` |
| OpenAI | `low/1536-x-1024/gpt-image-1.5-2025-12-16` |
| OpenAI | `medium/1024-x-1024/gpt-image-1` |
| OpenAI | `medium/1024-x-1024/gpt-image-1-mini` |
| OpenAI | `medium/1024-x-1024/gpt-image-1.5` |
| OpenAI | `medium/1024-x-1024/gpt-image-1.5-2025-12-16` |
| OpenAI | `medium/1024-x-1536/gpt-image-1` |
| OpenAI | `medium/1024-x-1536/gpt-image-1-mini` |
| OpenAI | `medium/1024-x-1536/gpt-image-1.5` |
| OpenAI | `medium/1024-x-1536/gpt-image-1.5-2025-12-16` |
| OpenAI | `medium/1536-x-1024/gpt-image-1` |
| OpenAI | `medium/1536-x-1024/gpt-image-1-mini` |
| OpenAI | `medium/1536-x-1024/gpt-image-1.5` |
| OpenAI | `medium/1536-x-1024/gpt-image-1.5-2025-12-16` |
| OpenAI | `o1` |
| OpenAI | `o1-2024-12-17` |
| OpenAI | `o1-mini` |
| OpenAI | `o1-preview` |
| OpenAI | `o1-pro` |
| OpenAI | `o1-pro-2025-03-19` |
| OpenAI | `o3` |
| OpenAI | `o3-2025-04-16` |
| OpenAI | `o3-deep-research` |
| OpenAI | `o3-deep-research-2025-06-26` |
| OpenAI | `o3-mini` |
| OpenAI | `o3-mini-2025-01-31` |
| OpenAI | `o3-pro` |
| OpenAI | `o3-pro-2025-06-10` |
| OpenAI | `o4-mini` |
| OpenAI | `o4-mini-2025-04-16` |
| OpenAI | `o4-mini-deep-research` |
| OpenAI | `o4-mini-deep-research-2025-06-26` |
| OpenAI | `omni-moderation-2024-09-26` |
| OpenAI | `omni-moderation-latest` |
| OpenAI | `openai/container` |
| OpenAI | `openai/sora-2` |
| OpenAI | `openai/sora-2-pro` |
| OpenAI | `openai/sora-2-pro-high-res` |
| OpenAI | `sora-2` |
| OpenAI | `sora-2-pro` |
| OpenAI | `sora-2-pro-high-res` |
| OpenAI | `standard/1024-x-1024/dall-e-3` |
| OpenAI | `standard/1024-x-1024/gpt-image-1.5` |
| OpenAI | `standard/1024-x-1024/gpt-image-1.5-2025-12-16` |
| OpenAI | `standard/1024-x-1536/gpt-image-1.5` |
| OpenAI | `standard/1024-x-1536/gpt-image-1.5-2025-12-16` |
| OpenAI | `standard/1024-x-1792/dall-e-3` |
| OpenAI | `standard/1536-x-1024/gpt-image-1.5` |
| OpenAI | `standard/1536-x-1024/gpt-image-1.5-2025-12-16` |
| OpenAI | `standard/1792-x-1024/dall-e-3` |
| OpenAI | `text-embedding-3-large` |
| OpenAI | `text-embedding-3-small` |
| OpenAI | `text-embedding-ada-002` |
| OpenAI | `text-embedding-ada-002-v2` |
| OpenAI | `text-moderation-007` |
| OpenAI | `text-moderation-latest` |
| OpenAI | `text-moderation-stable` |
| OpenAI | `tts-1` |
| OpenAI | `tts-1-1106` |
| OpenAI | `tts-1-hd` |
| OpenAI | `tts-1-hd-1106` |
| OpenAI | `whisper-1` |
| OpenRouter | `ai21/jamba-large-1.7` |
| OpenRouter | `aion-labs/aion-1.0` |
| OpenRouter | `aion-labs/aion-1.0-mini` |
| OpenRouter | `aion-labs/aion-2.0` |
| OpenRouter | `aion-labs/aion-rp-llama-3.1-8b` |
| OpenRouter | `allenai/olmo-3-32b-think` |
| OpenRouter | `amazon/nova-2-lite-v1` |
| OpenRouter | `amazon/nova-lite-v1` |
| OpenRouter | `amazon/nova-micro-v1` |
| OpenRouter | `amazon/nova-premier-v1` |
| OpenRouter | `amazon/nova-pro-v1` |
| OpenRouter | `anthracite-org/magnum-v4-72b` |
| OpenRouter | `anthropic/claude-3-haiku` |
| OpenRouter | `anthropic/claude-3.5-haiku` |
| OpenRouter | `anthropic/claude-haiku-4.5` |
| OpenRouter | `anthropic/claude-opus-4` |
| OpenRouter | `anthropic/claude-opus-4.1` |
| OpenRouter | `anthropic/claude-opus-4.5` |
| OpenRouter | `anthropic/claude-opus-4.6` |
| OpenRouter | `anthropic/claude-opus-4.6-fast` |
| OpenRouter | `anthropic/claude-opus-4.7` |
| OpenRouter | `anthropic/claude-opus-4.7-fast` |
| OpenRouter | `anthropic/claude-opus-4.8` |
| OpenRouter | `anthropic/claude-opus-4.8-fast` |
| OpenRouter | `anthropic/claude-sonnet-4` |
| OpenRouter | `anthropic/claude-sonnet-4.5` |
| OpenRouter | `anthropic/claude-sonnet-4.6` |
| OpenRouter | `arcee-ai/coder-large` |
| OpenRouter | `arcee-ai/maestro-reasoning` |
| OpenRouter | `arcee-ai/spotlight` |
| OpenRouter | `arcee-ai/trinity-large-thinking` |
| OpenRouter | `arcee-ai/trinity-mini` |
| OpenRouter | `arcee-ai/virtuoso-large` |
| OpenRouter | `baidu/ernie-4.5-vl-28b-a3b` |
| OpenRouter | `baidu/ernie-4.5-vl-424b-a47b` |
| OpenRouter | `bytedance-seed/seed-1.6` |
| OpenRouter | `bytedance-seed/seed-1.6-flash` |
| OpenRouter | `bytedance-seed/seed-2.0-lite` |
| OpenRouter | `bytedance-seed/seed-2.0-mini` |
| OpenRouter | `bytedance/ui-tars-1.5-7b` |
| OpenRouter | `cognitivecomputations/dolphin-mistral-24b-venice-edition:free` |
| OpenRouter | `cohere/command-a` |
| OpenRouter | `cohere/command-r-08-2024` |
| OpenRouter | `cohere/command-r-plus-08-2024` |
| OpenRouter | `cohere/command-r7b-12-2024` |
| OpenRouter | `deepcogito/cogito-v2.1-671b` |
| OpenRouter | `deepseek/deepseek-chat` |
| OpenRouter | `deepseek/deepseek-chat-v3-0324` |
| OpenRouter | `deepseek/deepseek-chat-v3.1` |
| OpenRouter | `deepseek/deepseek-r1` |
| OpenRouter | `deepseek/deepseek-r1-0528` |
| OpenRouter | `deepseek/deepseek-r1-distill-llama-70b` |
| OpenRouter | `deepseek/deepseek-r1-distill-qwen-32b` |
| OpenRouter | `deepseek/deepseek-v3.1-terminus` |
| OpenRouter | `deepseek/deepseek-v3.2` |
| OpenRouter | `deepseek/deepseek-v3.2-exp` |
| OpenRouter | `deepseek/deepseek-v4-flash` |
| OpenRouter | `deepseek/deepseek-v4-pro` |
| OpenRouter | `essentialai/rnj-1-instruct` |
| OpenRouter | `google/gemini-2.5-flash` |
| OpenRouter | `google/gemini-2.5-flash-image` |
| OpenRouter | `google/gemini-2.5-flash-lite` |
| OpenRouter | `google/gemini-2.5-flash-lite-preview-09-2025` |
| OpenRouter | `google/gemini-2.5-pro` |
| OpenRouter | `google/gemini-2.5-pro-preview` |
| OpenRouter | `google/gemini-2.5-pro-preview-05-06` |
| OpenRouter | `google/gemini-3-flash-preview` |
| OpenRouter | `google/gemini-3-pro-image-preview` |
| OpenRouter | `google/gemini-3.1-flash-image-preview` |
| OpenRouter | `google/gemini-3.1-flash-lite` |
| OpenRouter | `google/gemini-3.1-flash-lite-preview` |
| OpenRouter | `google/gemini-3.1-pro-preview` |
| OpenRouter | `google/gemini-3.1-pro-preview-customtools` |
| OpenRouter | `google/gemini-3.5-flash` |
| OpenRouter | `google/gemma-2-27b-it` |
| OpenRouter | `google/gemma-3-12b-it` |
| OpenRouter | `google/gemma-3-27b-it` |
| OpenRouter | `google/gemma-3-4b-it` |
| OpenRouter | `google/gemma-3n-e4b-it` |
| OpenRouter | `google/gemma-4-26b-a4b-it` |
| OpenRouter | `google/gemma-4-26b-a4b-it:free` |
| OpenRouter | `google/gemma-4-31b-it` |
| OpenRouter | `google/gemma-4-31b-it:free` |
| OpenRouter | `google/lyria-3-clip-preview` |
| OpenRouter | `google/lyria-3-pro-preview` |
| OpenRouter | `gryphe/mythomax-l2-13b` |
| OpenRouter | `ibm-granite/granite-4.0-h-micro` |
| OpenRouter | `ibm-granite/granite-4.1-8b` |
| OpenRouter | `inception/mercury-2` |
| OpenRouter | `inclusionai/ling-2.6-1t` |
| OpenRouter | `inclusionai/ling-2.6-flash` |
| OpenRouter | `inclusionai/ring-2.6-1t` |
| OpenRouter | `inflection/inflection-3-pi` |
| OpenRouter | `inflection/inflection-3-productivity` |
| OpenRouter | `kwaipilot/kat-coder-pro-v2` |
| OpenRouter | `liquid/lfm-2-24b-a2b` |
| OpenRouter | `liquid/lfm-2.5-1.2b-instruct:free` |
| OpenRouter | `liquid/lfm-2.5-1.2b-thinking:free` |
| OpenRouter | `mancer/weaver` |
| OpenRouter | `meta-llama/llama-3-70b-instruct` |
| OpenRouter | `meta-llama/llama-3-8b-instruct` |
| OpenRouter | `meta-llama/llama-3.1-70b-instruct` |
| OpenRouter | `meta-llama/llama-3.1-8b-instruct` |
| OpenRouter | `meta-llama/llama-3.2-11b-vision-instruct` |
| OpenRouter | `meta-llama/llama-3.2-1b-instruct` |
| OpenRouter | `meta-llama/llama-3.2-3b-instruct` |
| OpenRouter | `meta-llama/llama-3.2-3b-instruct:free` |
| OpenRouter | `meta-llama/llama-3.3-70b-instruct` |
| OpenRouter | `meta-llama/llama-3.3-70b-instruct:free` |
| OpenRouter | `meta-llama/llama-4-maverick` |
| OpenRouter | `meta-llama/llama-4-scout` |
| OpenRouter | `meta-llama/llama-guard-3-8b` |
| OpenRouter | `meta-llama/llama-guard-4-12b` |
| OpenRouter | `microsoft/phi-4` |
| OpenRouter | `microsoft/phi-4-mini-instruct` |
| OpenRouter | `microsoft/wizardlm-2-8x22b` |
| OpenRouter | `minimax/minimax-01` |
| OpenRouter | `minimax/minimax-m1` |
| OpenRouter | `minimax/minimax-m2` |
| OpenRouter | `minimax/minimax-m2-her` |
| OpenRouter | `minimax/minimax-m2.1` |
| OpenRouter | `minimax/minimax-m2.5` |
| OpenRouter | `minimax/minimax-m2.7` |
| OpenRouter | `minimax/minimax-m3` |
| OpenRouter | `mistralai/codestral-2508` |
| OpenRouter | `mistralai/devstral-2512` |
| OpenRouter | `mistralai/ministral-14b-2512` |
| OpenRouter | `mistralai/ministral-3b-2512` |
| OpenRouter | `mistralai/ministral-8b-2512` |
| OpenRouter | `mistralai/mistral-large` |
| OpenRouter | `mistralai/mistral-large-2407` |
| OpenRouter | `mistralai/mistral-large-2512` |
| OpenRouter | `mistralai/mistral-medium-3` |
| OpenRouter | `mistralai/mistral-medium-3-5` |
| OpenRouter | `mistralai/mistral-medium-3.1` |
| OpenRouter | `mistralai/mistral-nemo` |
| OpenRouter | `mistralai/mistral-saba` |
| OpenRouter | `mistralai/mistral-small-24b-instruct-2501` |
| OpenRouter | `mistralai/mistral-small-2603` |
| OpenRouter | `mistralai/mistral-small-3.1-24b-instruct` |
| OpenRouter | `mistralai/mistral-small-3.2-24b-instruct` |
| OpenRouter | `mistralai/mixtral-8x22b-instruct` |
| OpenRouter | `mistralai/voxtral-small-24b-2507` |
| OpenRouter | `moonshotai/kimi-k2` |
| OpenRouter | `moonshotai/kimi-k2-0905` |
| OpenRouter | `moonshotai/kimi-k2-thinking` |
| OpenRouter | `moonshotai/kimi-k2.5` |
| OpenRouter | `moonshotai/kimi-k2.6` |
| OpenRouter | `moonshotai/kimi-k2.6:free` |
| OpenRouter | `morph/morph-v3-fast` |
| OpenRouter | `morph/morph-v3-large` |
| OpenRouter | `nex-agi/deepseek-v3.1-nex-n1` |
| OpenRouter | `nousresearch/hermes-2-pro-llama-3-8b` |
| OpenRouter | `nousresearch/hermes-3-llama-3.1-405b` |
| OpenRouter | `nousresearch/hermes-3-llama-3.1-405b:free` |
| OpenRouter | `nousresearch/hermes-3-llama-3.1-70b` |
| OpenRouter | `nousresearch/hermes-4-405b` |
| OpenRouter | `nousresearch/hermes-4-70b` |
| OpenRouter | `nvidia/llama-3.3-nemotron-super-49b-v1.5` |
| OpenRouter | `nvidia/nemotron-3-nano-30b-a3b` |
| OpenRouter | `nvidia/nemotron-3-nano-30b-a3b:free` |
| OpenRouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` |
| OpenRouter | `nvidia/nemotron-3-super-120b-a12b` |
| OpenRouter | `nvidia/nemotron-3-super-120b-a12b:free` |
| OpenRouter | `nvidia/nemotron-nano-12b-v2-vl:free` |
| OpenRouter | `nvidia/nemotron-nano-9b-v2` |
| OpenRouter | `nvidia/nemotron-nano-9b-v2:free` |
| OpenRouter | `openai/gpt-3.5-turbo` |
| OpenRouter | `openai/gpt-3.5-turbo-0613` |
| OpenRouter | `openai/gpt-3.5-turbo-16k` |
| OpenRouter | `openai/gpt-3.5-turbo-instruct` |
| OpenRouter | `openai/gpt-4` |
| OpenRouter | `openai/gpt-4-0314` |
| OpenRouter | `openai/gpt-4-1106-preview` |
| OpenRouter | `openai/gpt-4-turbo` |
| OpenRouter | `openai/gpt-4-turbo-preview` |
| OpenRouter | `openai/gpt-4.1` |
| OpenRouter | `openai/gpt-4.1-mini` |
| OpenRouter | `openai/gpt-4.1-nano` |
| OpenRouter | `openai/gpt-4o` |
| OpenRouter | `openai/gpt-4o-2024-05-13` |
| OpenRouter | `openai/gpt-4o-2024-08-06` |
| OpenRouter | `openai/gpt-4o-2024-11-20` |
| OpenRouter | `openai/gpt-4o-mini` |
| OpenRouter | `openai/gpt-4o-mini-2024-07-18` |
| OpenRouter | `openai/gpt-4o-mini-search-preview` |
| OpenRouter | `openai/gpt-4o-search-preview` |
| OpenRouter | `openai/gpt-5` |
| OpenRouter | `openai/gpt-5-chat` |
| OpenRouter | `openai/gpt-5-codex` |
| OpenRouter | `openai/gpt-5-image` |
| OpenRouter | `openai/gpt-5-image-mini` |
| OpenRouter | `openai/gpt-5-mini` |
| OpenRouter | `openai/gpt-5-nano` |
| OpenRouter | `openai/gpt-5-pro` |
| OpenRouter | `openai/gpt-5.1` |
| OpenRouter | `openai/gpt-5.1-chat` |
| OpenRouter | `openai/gpt-5.1-codex` |
| OpenRouter | `openai/gpt-5.1-codex-max` |
| OpenRouter | `openai/gpt-5.1-codex-mini` |
| OpenRouter | `openai/gpt-5.2` |
| OpenRouter | `openai/gpt-5.2-chat` |
| OpenRouter | `openai/gpt-5.2-codex` |
| OpenRouter | `openai/gpt-5.2-pro` |
| OpenRouter | `openai/gpt-5.3-chat` |
| OpenRouter | `openai/gpt-5.3-codex` |
| OpenRouter | `openai/gpt-5.4` |
| OpenRouter | `openai/gpt-5.4-image-2` |
| OpenRouter | `openai/gpt-5.4-mini` |
| OpenRouter | `openai/gpt-5.4-nano` |
| OpenRouter | `openai/gpt-5.4-pro` |
| OpenRouter | `openai/gpt-5.5` |
| OpenRouter | `openai/gpt-5.5-pro` |
| OpenRouter | `openai/gpt-audio` |
| OpenRouter | `openai/gpt-audio-mini` |
| OpenRouter | `openai/gpt-chat-latest` |
| OpenRouter | `openai/gpt-oss-120b` |
| OpenRouter | `openai/gpt-oss-120b:free` |
| OpenRouter | `openai/gpt-oss-20b` |
| OpenRouter | `openai/gpt-oss-20b:free` |
| OpenRouter | `openai/gpt-oss-safeguard-20b` |
| OpenRouter | `openai/o1` |
| OpenRouter | `openai/o1-pro` |
| OpenRouter | `openai/o3` |
| OpenRouter | `openai/o3-deep-research` |
| OpenRouter | `openai/o3-mini` |
| OpenRouter | `openai/o3-mini-high` |
| OpenRouter | `openai/o3-pro` |
| OpenRouter | `openai/o4-mini` |
| OpenRouter | `openai/o4-mini-deep-research` |
| OpenRouter | `openai/o4-mini-high` |
| OpenRouter | `openrouter/anthropic/claude-3-haiku` |
| OpenRouter | `openrouter/anthropic/claude-3.5-sonnet` |
| OpenRouter | `openrouter/anthropic/claude-3.7-sonnet` |
| OpenRouter | `openrouter/anthropic/claude-haiku-4.5` |
| OpenRouter | `openrouter/anthropic/claude-opus-4` |
| OpenRouter | `openrouter/anthropic/claude-opus-4.1` |
| OpenRouter | `openrouter/anthropic/claude-opus-4.5` |
| OpenRouter | `openrouter/anthropic/claude-opus-4.6` |
| OpenRouter | `openrouter/anthropic/claude-opus-4.7` |
| OpenRouter | `openrouter/anthropic/claude-sonnet-4` |
| OpenRouter | `openrouter/anthropic/claude-sonnet-4.5` |
| OpenRouter | `openrouter/anthropic/claude-sonnet-4.6` |
| OpenRouter | `openrouter/auto` |
| OpenRouter | `openrouter/bodybuilder` |
| OpenRouter | `openrouter/bytedance/ui-tars-1.5-7b` |
| OpenRouter | `openrouter/deepseek/deepseek-chat` |
| OpenRouter | `openrouter/deepseek/deepseek-chat-v3-0324` |
| OpenRouter | `openrouter/deepseek/deepseek-chat-v3.1` |
| OpenRouter | `openrouter/deepseek/deepseek-r1` |
| OpenRouter | `openrouter/deepseek/deepseek-r1-0528` |
| OpenRouter | `openrouter/deepseek/deepseek-v3.2` |
| OpenRouter | `openrouter/deepseek/deepseek-v3.2-exp` |
| OpenRouter | `openrouter/free` |
| OpenRouter | `openrouter/fusion` |
| OpenRouter | `openrouter/google/gemini-2.0-flash-001` |
| OpenRouter | `openrouter/google/gemini-2.5-flash` |
| OpenRouter | `openrouter/google/gemini-2.5-pro` |
| OpenRouter | `openrouter/google/gemini-3-flash-preview` |
| OpenRouter | `openrouter/google/gemini-3-pro-preview` |
| OpenRouter | `openrouter/google/gemini-3.1-flash-lite` |
| OpenRouter | `openrouter/google/gemini-3.1-flash-lite-preview` |
| OpenRouter | `openrouter/google/gemini-3.1-pro-preview` |
| OpenRouter | `openrouter/gryphe/mythomax-l2-13b` |
| OpenRouter | `openrouter/mancer/weaver` |
| OpenRouter | `openrouter/meta-llama/llama-3-70b-instruct` |
| OpenRouter | `openrouter/minimax/minimax-m2` |
| OpenRouter | `openrouter/minimax/minimax-m2.1` |
| OpenRouter | `openrouter/minimax/minimax-m2.5` |
| OpenRouter | `openrouter/mistralai/devstral-2512` |
| OpenRouter | `openrouter/mistralai/ministral-14b-2512` |
| OpenRouter | `openrouter/mistralai/ministral-3b-2512` |
| OpenRouter | `openrouter/mistralai/ministral-8b-2512` |
| OpenRouter | `openrouter/mistralai/mistral-7b-instruct` |
| OpenRouter | `openrouter/mistralai/mistral-large` |
| OpenRouter | `openrouter/mistralai/mistral-large-2512` |
| OpenRouter | `openrouter/mistralai/mistral-small-3.1-24b-instruct` |
| OpenRouter | `openrouter/mistralai/mistral-small-3.2-24b-instruct` |
| OpenRouter | `openrouter/mistralai/mixtral-8x22b-instruct` |
| OpenRouter | `openrouter/moonshotai/kimi-k2.5` |
| OpenRouter | `openrouter/openai/gpt-3.5-turbo` |
| OpenRouter | `openrouter/openai/gpt-3.5-turbo-16k` |
| OpenRouter | `openrouter/openai/gpt-4` |
| OpenRouter | `openrouter/openai/gpt-4.1` |
| OpenRouter | `openrouter/openai/gpt-4.1-mini` |
| OpenRouter | `openrouter/openai/gpt-4.1-nano` |
| OpenRouter | `openrouter/openai/gpt-4o` |
| OpenRouter | `openrouter/openai/gpt-4o-2024-05-13` |
| OpenRouter | `openrouter/openai/gpt-5` |
| OpenRouter | `openrouter/openai/gpt-5-chat` |
| OpenRouter | `openrouter/openai/gpt-5-codex` |
| OpenRouter | `openrouter/openai/gpt-5-mini` |
| OpenRouter | `openrouter/openai/gpt-5-nano` |
| OpenRouter | `openrouter/openai/gpt-5.1-codex-max` |
| OpenRouter | `openrouter/openai/gpt-5.2` |
| OpenRouter | `openrouter/openai/gpt-5.2-chat` |
| OpenRouter | `openrouter/openai/gpt-5.2-codex` |
| OpenRouter | `openrouter/openai/gpt-5.2-pro` |
| OpenRouter | `openrouter/openai/gpt-oss-120b` |
| OpenRouter | `openrouter/openai/gpt-oss-20b` |
| OpenRouter | `openrouter/openai/o1` |
| OpenRouter | `openrouter/openai/o3-mini` |
| OpenRouter | `openrouter/openai/o3-mini-high` |
| OpenRouter | `openrouter/openrouter/auto` |
| OpenRouter | `openrouter/openrouter/bodybuilder` |
| OpenRouter | `openrouter/openrouter/free` |
| OpenRouter | `openrouter/owl-alpha` |
| OpenRouter | `openrouter/pareto-code` |
| OpenRouter | `openrouter/qwen/qwen-2.5-coder-32b-instruct` |
| OpenRouter | `openrouter/qwen/qwen-vl-plus` |
| OpenRouter | `openrouter/qwen/qwen3-235b-a22b-2507` |
| OpenRouter | `openrouter/qwen/qwen3-235b-a22b-thinking-2507` |
| OpenRouter | `openrouter/qwen/qwen3-coder` |
| OpenRouter | `openrouter/qwen/qwen3-coder-plus` |
| OpenRouter | `openrouter/qwen/qwen3.5-122b-a10b` |
| OpenRouter | `openrouter/qwen/qwen3.5-27b` |
| OpenRouter | `openrouter/qwen/qwen3.5-35b-a3b` |
| OpenRouter | `openrouter/qwen/qwen3.5-397b-a17b` |
| OpenRouter | `openrouter/qwen/qwen3.5-flash-02-23` |
| OpenRouter | `openrouter/qwen/qwen3.5-plus-02-15` |
| OpenRouter | `openrouter/qwen/qwen3.6-plus` |
| OpenRouter | `openrouter/switchpoint/router` |
| OpenRouter | `openrouter/undi95/remm-slerp-l2-13b` |
| OpenRouter | `openrouter/x-ai/grok-4` |
| OpenRouter | `openrouter/xiaomi/mimo-v2-flash` |
| OpenRouter | `openrouter/xiaomi/mimo-v2.5` |
| OpenRouter | `openrouter/xiaomi/mimo-v2.5-pro` |
| OpenRouter | `openrouter/z-ai/glm-4.6` |
| OpenRouter | `openrouter/z-ai/glm-4.6:exacto` |
| OpenRouter | `openrouter/z-ai/glm-4.7` |
| OpenRouter | `openrouter/z-ai/glm-4.7-flash` |
| OpenRouter | `openrouter/z-ai/glm-5` |
| OpenRouter | `perceptron/perceptron-mk1` |
| OpenRouter | `perplexity/sonar` |
| OpenRouter | `perplexity/sonar-deep-research` |
| OpenRouter | `perplexity/sonar-pro` |
| OpenRouter | `perplexity/sonar-pro-search` |
| OpenRouter | `perplexity/sonar-reasoning-pro` |
| OpenRouter | `poolside/laguna-m.1:free` |
| OpenRouter | `poolside/laguna-xs.2:free` |
| OpenRouter | `prime-intellect/intellect-3` |
| OpenRouter | `qwen/qwen-2.5-72b-instruct` |
| OpenRouter | `qwen/qwen-2.5-7b-instruct` |
| OpenRouter | `qwen/qwen-2.5-coder-32b-instruct` |
| OpenRouter | `qwen/qwen-plus` |
| OpenRouter | `qwen/qwen-plus-2025-07-28` |
| OpenRouter | `qwen/qwen-plus-2025-07-28:thinking` |
| OpenRouter | `qwen/qwen2.5-vl-72b-instruct` |
| OpenRouter | `qwen/qwen3-14b` |
| OpenRouter | `qwen/qwen3-235b-a22b` |
| OpenRouter | `qwen/qwen3-235b-a22b-2507` |
| OpenRouter | `qwen/qwen3-235b-a22b-thinking-2507` |
| OpenRouter | `qwen/qwen3-30b-a3b` |
| OpenRouter | `qwen/qwen3-30b-a3b-instruct-2507` |
| OpenRouter | `qwen/qwen3-30b-a3b-thinking-2507` |
| OpenRouter | `qwen/qwen3-32b` |
| OpenRouter | `qwen/qwen3-8b` |
| OpenRouter | `qwen/qwen3-coder` |
| OpenRouter | `qwen/qwen3-coder-30b-a3b-instruct` |
| OpenRouter | `qwen/qwen3-coder-flash` |
| OpenRouter | `qwen/qwen3-coder-next` |
| OpenRouter | `qwen/qwen3-coder-plus` |
| OpenRouter | `qwen/qwen3-coder:free` |
| OpenRouter | `qwen/qwen3-max` |
| OpenRouter | `qwen/qwen3-max-thinking` |
| OpenRouter | `qwen/qwen3-next-80b-a3b-instruct` |
| OpenRouter | `qwen/qwen3-next-80b-a3b-instruct:free` |
| OpenRouter | `qwen/qwen3-next-80b-a3b-thinking` |
| OpenRouter | `qwen/qwen3-vl-235b-a22b-instruct` |
| OpenRouter | `qwen/qwen3-vl-235b-a22b-thinking` |
| OpenRouter | `qwen/qwen3-vl-30b-a3b-instruct` |
| OpenRouter | `qwen/qwen3-vl-30b-a3b-thinking` |
| OpenRouter | `qwen/qwen3-vl-32b-instruct` |
| OpenRouter | `qwen/qwen3-vl-8b-instruct` |
| OpenRouter | `qwen/qwen3-vl-8b-thinking` |
| OpenRouter | `qwen/qwen3.5-122b-a10b` |
| OpenRouter | `qwen/qwen3.5-27b` |
| OpenRouter | `qwen/qwen3.5-35b-a3b` |
| OpenRouter | `qwen/qwen3.5-397b-a17b` |
| OpenRouter | `qwen/qwen3.5-9b` |
| OpenRouter | `qwen/qwen3.5-flash-02-23` |
| OpenRouter | `qwen/qwen3.5-plus-02-15` |
| OpenRouter | `qwen/qwen3.5-plus-20260420` |
| OpenRouter | `qwen/qwen3.6-27b` |
| OpenRouter | `qwen/qwen3.6-35b-a3b` |
| OpenRouter | `qwen/qwen3.6-flash` |
| OpenRouter | `qwen/qwen3.6-max-preview` |
| OpenRouter | `qwen/qwen3.6-plus` |
| OpenRouter | `qwen/qwen3.7-max` |
| OpenRouter | `qwen/qwen3.7-plus` |
| OpenRouter | `rekaai/reka-edge` |
| OpenRouter | `rekaai/reka-flash-3` |
| OpenRouter | `relace/relace-apply-3` |
| OpenRouter | `relace/relace-search` |
| OpenRouter | `sao10k/l3-euryale-70b` |
| OpenRouter | `sao10k/l3-lunaris-8b` |
| OpenRouter | `sao10k/l3.1-70b-hanami-x1` |
| OpenRouter | `sao10k/l3.1-euryale-70b` |
| OpenRouter | `sao10k/l3.3-euryale-70b` |
| OpenRouter | `stepfun/step-3.5-flash` |
| OpenRouter | `stepfun/step-3.7-flash` |
| OpenRouter | `switchpoint/router` |
| OpenRouter | `tencent/hunyuan-a13b-instruct` |
| OpenRouter | `tencent/hy3-preview` |
| OpenRouter | `thedrummer/cydonia-24b-v4.1` |
| OpenRouter | `thedrummer/rocinante-12b` |
| OpenRouter | `thedrummer/skyfall-36b-v2` |
| OpenRouter | `thedrummer/unslopnemo-12b` |
| OpenRouter | `undi95/remm-slerp-l2-13b` |
| OpenRouter | `upstage/solar-pro-3` |
| OpenRouter | `writer/palmyra-x5` |
| OpenRouter | `x-ai/grok-4.20` |
| OpenRouter | `x-ai/grok-4.20-multi-agent` |
| OpenRouter | `x-ai/grok-4.3` |
| OpenRouter | `x-ai/grok-build-0.1` |
| OpenRouter | `xiaomi/mimo-v2-flash` |
| OpenRouter | `xiaomi/mimo-v2.5` |
| OpenRouter | `xiaomi/mimo-v2.5-pro` |
| OpenRouter | `z-ai/glm-4-32b` |
| OpenRouter | `z-ai/glm-4.5` |
| OpenRouter | `z-ai/glm-4.5-air` |
| OpenRouter | `z-ai/glm-4.5-air:free` |
| OpenRouter | `z-ai/glm-4.5v` |
| OpenRouter | `z-ai/glm-4.6` |
| OpenRouter | `z-ai/glm-4.6v` |
| OpenRouter | `z-ai/glm-4.7` |
| OpenRouter | `z-ai/glm-4.7-flash` |
| OpenRouter | `z-ai/glm-5` |
| OpenRouter | `z-ai/glm-5-turbo` |
| OpenRouter | `z-ai/glm-5.1` |
| OpenRouter | `z-ai/glm-5v-turbo` |
| OpenRouter | `~anthropic/claude-haiku-latest` |
| OpenRouter | `~anthropic/claude-opus-latest` |
| OpenRouter | `~anthropic/claude-sonnet-latest` |
| OpenRouter | `~google/gemini-flash-latest` |
| OpenRouter | `~google/gemini-pro-latest` |
| OpenRouter | `~moonshotai/kimi-latest` |
| OpenRouter | `~openai/gpt-latest` |
| OpenRouter | `~openai/gpt-mini-latest` |
| Perplexity | `perplexity/anthropic/claude-haiku-4-5` |
| Perplexity | `perplexity/anthropic/claude-opus-4-5` |
| Perplexity | `perplexity/anthropic/claude-opus-4-6` |
| Perplexity | `perplexity/anthropic/claude-opus-4-7` |
| Perplexity | `perplexity/anthropic/claude-sonnet-4-5` |
| Perplexity | `perplexity/codellama-34b-instruct` |
| Perplexity | `perplexity/codellama-70b-instruct` |
| Perplexity | `perplexity/google/gemini-2.5-flash` |
| Perplexity | `perplexity/google/gemini-2.5-pro` |
| Perplexity | `perplexity/google/gemini-3-flash-preview` |
| Perplexity | `perplexity/google/gemini-3-pro-preview` |
| Perplexity | `perplexity/llama-2-70b-chat` |
| Perplexity | `perplexity/llama-3.1-70b-instruct` |
| Perplexity | `perplexity/llama-3.1-8b-instruct` |
| Perplexity | `perplexity/mistral-7b-instruct` |
| Perplexity | `perplexity/mixtral-8x7b-instruct` |
| Perplexity | `perplexity/openai/gpt-5-mini` |
| Perplexity | `perplexity/openai/gpt-5.1` |
| Perplexity | `perplexity/openai/gpt-5.2` |
| Perplexity | `perplexity/perplexity/sonar` |
| Perplexity | `perplexity/pplx-70b-chat` |
| Perplexity | `perplexity/pplx-70b-online` |
| Perplexity | `perplexity/pplx-7b-chat` |
| Perplexity | `perplexity/pplx-7b-online` |
| Perplexity | `perplexity/pplx-embed-v1-0.6b` |
| Perplexity | `perplexity/pplx-embed-v1-4b` |
| Perplexity | `perplexity/preset/advanced-deep-research` |
| Perplexity | `perplexity/preset/deep-research` |
| Perplexity | `perplexity/preset/fast-search` |
| Perplexity | `perplexity/preset/pro-search` |
| Perplexity | `perplexity/search` |
| Perplexity | `perplexity/sonar` |
| Perplexity | `perplexity/sonar-deep-research` |
| Perplexity | `perplexity/sonar-medium-chat` |
| Perplexity | `perplexity/sonar-medium-online` |
| Perplexity | `perplexity/sonar-pro` |
| Perplexity | `perplexity/sonar-reasoning` |
| Perplexity | `perplexity/sonar-reasoning-pro` |
| Perplexity | `perplexity/sonar-small-chat` |
| Perplexity | `perplexity/sonar-small-online` |
| Perplexity | `perplexity/xai/grok-4-1-fast-non-reasoning` |
| Perplexity | `sonar` |
| Perplexity | `sonar-deep-research` |
| Perplexity | `sonar-pro` |
| Perplexity | `sonar-reasoning-pro` |
| Poolside | `poolside/laguna-m.1` |
| Poolside | `poolside/laguna-xs.2` |
| Alibaba / Qwen | `MiniMax-M2.5` |
| Alibaba / Qwen | `MiniMax/MiniMax-M2.7` |
| Alibaba / Qwen | `dashscope/qwen-coder` |
| Alibaba / Qwen | `dashscope/qwen-flash` |
| Alibaba / Qwen | `dashscope/qwen-flash-2025-07-28` |
| Alibaba / Qwen | `dashscope/qwen-image-2.0` |
| Alibaba / Qwen | `dashscope/qwen-image-2.0-pro` |
| Alibaba / Qwen | `dashscope/qwen-max` |
| Alibaba / Qwen | `dashscope/qwen-plus` |
| Alibaba / Qwen | `dashscope/qwen-plus-2025-01-25` |
| Alibaba / Qwen | `dashscope/qwen-plus-2025-04-28` |
| Alibaba / Qwen | `dashscope/qwen-plus-2025-07-14` |
| Alibaba / Qwen | `dashscope/qwen-plus-2025-07-28` |
| Alibaba / Qwen | `dashscope/qwen-plus-2025-09-11` |
| Alibaba / Qwen | `dashscope/qwen-plus-latest` |
| Alibaba / Qwen | `dashscope/qwen-turbo` |
| Alibaba / Qwen | `dashscope/qwen-turbo-2024-11-01` |
| Alibaba / Qwen | `dashscope/qwen-turbo-2025-04-28` |
| Alibaba / Qwen | `dashscope/qwen-turbo-latest` |
| Alibaba / Qwen | `dashscope/qwen3-30b-a3b` |
| Alibaba / Qwen | `dashscope/qwen3-coder-flash` |
| Alibaba / Qwen | `dashscope/qwen3-coder-flash-2025-07-28` |
| Alibaba / Qwen | `dashscope/qwen3-coder-plus` |
| Alibaba / Qwen | `dashscope/qwen3-coder-plus-2025-07-22` |
| Alibaba / Qwen | `dashscope/qwen3-max` |
| Alibaba / Qwen | `dashscope/qwen3-max-2026-01-23` |
| Alibaba / Qwen | `dashscope/qwen3-max-preview` |
| Alibaba / Qwen | `dashscope/qwen3-next-80b-a3b-instruct` |
| Alibaba / Qwen | `dashscope/qwen3-next-80b-a3b-thinking` |
| Alibaba / Qwen | `dashscope/qwen3-vl-235b-a22b-instruct` |
| Alibaba / Qwen | `dashscope/qwen3-vl-235b-a22b-thinking` |
| Alibaba / Qwen | `dashscope/qwen3-vl-32b-instruct` |
| Alibaba / Qwen | `dashscope/qwen3-vl-32b-thinking` |
| Alibaba / Qwen | `dashscope/qwen3-vl-plus` |
| Alibaba / Qwen | `dashscope/qwen3.5-plus` |
| Alibaba / Qwen | `dashscope/qwq-plus` |
| Alibaba / Qwen | `deepseek-r1` |
| Alibaba / Qwen | `deepseek-r1-0528` |
| Alibaba / Qwen | `deepseek-r1-distill-llama-70b` |
| Alibaba / Qwen | `deepseek-r1-distill-llama-8b` |
| Alibaba / Qwen | `deepseek-r1-distill-qwen-1-5b` |
| Alibaba / Qwen | `deepseek-r1-distill-qwen-14b` |
| Alibaba / Qwen | `deepseek-r1-distill-qwen-32b` |
| Alibaba / Qwen | `deepseek-r1-distill-qwen-7b` |
| Alibaba / Qwen | `deepseek-v3` |
| Alibaba / Qwen | `deepseek-v3-1` |
| Alibaba / Qwen | `deepseek-v3-2-exp` |
| Alibaba / Qwen | `deepseek-v4-flash` |
| Alibaba / Qwen | `deepseek-v4-pro` |
| Alibaba / Qwen | `glm-5` |
| Alibaba / Qwen | `glm-5.1` |
| Alibaba / Qwen | `kimi-k2-thinking` |
| Alibaba / Qwen | `kimi-k2.5` |
| Alibaba / Qwen | `kimi-k2.6` |
| Alibaba / Qwen | `kimi/kimi-k2.5` |
| Alibaba / Qwen | `moonshot-kimi-k2-instruct` |
| Alibaba / Qwen | `qvq-max` |
| Alibaba / Qwen | `qwen-deep-research` |
| Alibaba / Qwen | `qwen-doc-turbo` |
| Alibaba / Qwen | `qwen-flash` |
| Alibaba / Qwen | `qwen-long` |
| Alibaba / Qwen | `qwen-math-plus` |
| Alibaba / Qwen | `qwen-math-turbo` |
| Alibaba / Qwen | `qwen-max` |
| Alibaba / Qwen | `qwen-mt-plus` |
| Alibaba / Qwen | `qwen-mt-turbo` |
| Alibaba / Qwen | `qwen-omni-turbo` |
| Alibaba / Qwen | `qwen-omni-turbo-realtime` |
| Alibaba / Qwen | `qwen-plus` |
| Alibaba / Qwen | `qwen-plus-character` |
| Alibaba / Qwen | `qwen-plus-character-ja` |
| Alibaba / Qwen | `qwen-turbo` |
| Alibaba / Qwen | `qwen-vl-max` |
| Alibaba / Qwen | `qwen-vl-ocr` |
| Alibaba / Qwen | `qwen-vl-plus` |
| Alibaba / Qwen | `qwen2-5-14b-instruct` |
| Alibaba / Qwen | `qwen2-5-32b-instruct` |
| Alibaba / Qwen | `qwen2-5-72b-instruct` |
| Alibaba / Qwen | `qwen2-5-7b-instruct` |
| Alibaba / Qwen | `qwen2-5-coder-32b-instruct` |
| Alibaba / Qwen | `qwen2-5-coder-7b-instruct` |
| Alibaba / Qwen | `qwen2-5-math-72b-instruct` |
| Alibaba / Qwen | `qwen2-5-math-7b-instruct` |
| Alibaba / Qwen | `qwen2-5-omni-7b` |
| Alibaba / Qwen | `qwen2-5-vl-72b-instruct` |
| Alibaba / Qwen | `qwen2-5-vl-7b-instruct` |
| Alibaba / Qwen | `qwen3-14b` |
| Alibaba / Qwen | `qwen3-235b-a22b` |
| Alibaba / Qwen | `qwen3-32b` |
| Alibaba / Qwen | `qwen3-8b` |
| Alibaba / Qwen | `qwen3-asr-flash` |
| Alibaba / Qwen | `qwen3-coder-30b-a3b-instruct` |
| Alibaba / Qwen | `qwen3-coder-480b-a35b-instruct` |
| Alibaba / Qwen | `qwen3-coder-flash` |
| Alibaba / Qwen | `qwen3-coder-plus` |
| Alibaba / Qwen | `qwen3-livetranslate-flash-realtime` |
| Alibaba / Qwen | `qwen3-max` |
| Alibaba / Qwen | `qwen3-next-80b-a3b-instruct` |
| Alibaba / Qwen | `qwen3-next-80b-a3b-thinking` |
| Alibaba / Qwen | `qwen3-omni-flash` |
| Alibaba / Qwen | `qwen3-omni-flash-realtime` |
| Alibaba / Qwen | `qwen3-vl-235b-a22b` |
| Alibaba / Qwen | `qwen3-vl-30b-a3b` |
| Alibaba / Qwen | `qwen3-vl-plus` |
| Alibaba / Qwen | `qwen3.5-122b-a10b` |
| Alibaba / Qwen | `qwen3.5-27b` |
| Alibaba / Qwen | `qwen3.5-35b-a3b` |
| Alibaba / Qwen | `qwen3.5-397b-a17b` |
| Alibaba / Qwen | `qwen3.5-flash` |
| Alibaba / Qwen | `qwen3.5-plus` |
| Alibaba / Qwen | `qwen3.6-27b` |
| Alibaba / Qwen | `qwen3.6-35b-a3b` |
| Alibaba / Qwen | `qwen3.6-flash` |
| Alibaba / Qwen | `qwen3.6-max-preview` |
| Alibaba / Qwen | `qwen3.6-plus` |
| Alibaba / Qwen | `qwen3.7-max` |
| Alibaba / Qwen | `qwen3.7-plus` |
| Alibaba / Qwen | `qwq-32b` |
| Alibaba / Qwen | `qwq-plus` |
| Alibaba / Qwen | `siliconflow/deepseek-r1-0528` |
| Alibaba / Qwen | `siliconflow/deepseek-v3-0324` |
| Alibaba / Qwen | `siliconflow/deepseek-v3.1-terminus` |
| Alibaba / Qwen | `siliconflow/deepseek-v3.2` |
| Alibaba / Qwen | `tongyi-intent-detect-v3` |
| Sarvam AI | `sarvam-105b` |
| Sarvam AI | `sarvam-30b` |
| Sarvam AI | `sarvam/sarvam-m` |
| Sber | `gigachat/Embeddings` |
| Sber | `gigachat/Embeddings-2` |
| Sber | `gigachat/EmbeddingsGigaR` |
| Sber | `gigachat/GigaChat-2-Lite` |
| Sber | `gigachat/GigaChat-2-Max` |
| Sber | `gigachat/GigaChat-2-Pro` |
| Snowflake | `snowflake/claude-3-5-sonnet` |
| Snowflake | `snowflake/deepseek-r1` |
| Snowflake | `snowflake/gemma-7b` |
| Snowflake | `snowflake/jamba-1.5-large` |
| Snowflake | `snowflake/jamba-1.5-mini` |
| Snowflake | `snowflake/jamba-instruct` |
| Snowflake | `snowflake/llama2-70b-chat` |
| Snowflake | `snowflake/llama3-70b` |
| Snowflake | `snowflake/llama3-8b` |
| Snowflake | `snowflake/llama3.1-405b` |
| Snowflake | `snowflake/llama3.1-70b` |
| Snowflake | `snowflake/llama3.1-8b` |
| Snowflake | `snowflake/llama3.2-1b` |
| Snowflake | `snowflake/llama3.2-3b` |
| Snowflake | `snowflake/llama3.3-70b` |
| Snowflake | `snowflake/mistral-7b` |
| Snowflake | `snowflake/mistral-large` |
| Snowflake | `snowflake/mistral-large2` |
| Snowflake | `snowflake/mixtral-8x7b` |
| Snowflake | `snowflake/reka-core` |
| Snowflake | `snowflake/reka-flash` |
| Snowflake | `snowflake/snowflake-arctic` |
| Snowflake | `snowflake/snowflake-llama-3.1-405b` |
| Snowflake | `snowflake/snowflake-llama-3.3-70b` |
| StepFun | `step-1-32k` |
| StepFun | `step-2-16k` |
| StepFun | `step-3.5-flash` |
| StepFun | `step-3.5-flash-2603` |
| Tencent | `glm-5` |
| Tencent | `hunyuan-2.0-instruct` |
| Tencent | `hunyuan-2.0-thinking` |
| Tencent | `hunyuan-t1` |
| Tencent | `hunyuan-turbos` |
| Tencent | `hy3-preview` |
| Tencent | `kimi-k2.5` |
| Tencent | `minimax-m2.5` |
| Tencent | `tc-code-latest` |
| Upstage | `solar-mini` |
| Upstage | `solar-pro2` |
| Upstage | `solar-pro3` |
| xAI | `grok-4.20-0309-non-reasoning` |
| xAI | `grok-4.20-0309-reasoning` |
| xAI | `grok-4.20-multi-agent-0309` |
| xAI | `grok-4.3` |
| xAI | `grok-build-0.1` |
| xAI | `grok-imagine-image` |
| xAI | `grok-imagine-image-quality` |
| xAI | `grok-imagine-video` |
| xAI | `xai/grok-2` |
| xAI | `xai/grok-2-1212` |
| xAI | `xai/grok-2-latest` |
| xAI | `xai/grok-2-vision` |
| xAI | `xai/grok-2-vision-1212` |
| xAI | `xai/grok-2-vision-latest` |
| xAI | `xai/grok-3` |
| xAI | `xai/grok-3-beta` |
| xAI | `xai/grok-3-fast-beta` |
| xAI | `xai/grok-3-fast-latest` |
| xAI | `xai/grok-3-latest` |
| xAI | `xai/grok-3-mini` |
| xAI | `xai/grok-3-mini-beta` |
| xAI | `xai/grok-3-mini-fast` |
| xAI | `xai/grok-3-mini-fast-beta` |
| xAI | `xai/grok-3-mini-fast-latest` |
| xAI | `xai/grok-3-mini-latest` |
| xAI | `xai/grok-4` |
| xAI | `xai/grok-4-0709` |
| xAI | `xai/grok-4-1-fast` |
| xAI | `xai/grok-4-1-fast-non-reasoning` |
| xAI | `xai/grok-4-1-fast-non-reasoning-latest` |
| xAI | `xai/grok-4-1-fast-reasoning` |
| xAI | `xai/grok-4-1-fast-reasoning-latest` |
| xAI | `xai/grok-4-fast-non-reasoning` |
| xAI | `xai/grok-4-fast-reasoning` |
| xAI | `xai/grok-4-latest` |
| xAI | `xai/grok-4.20-0309-reasoning` |
| xAI | `xai/grok-4.20-beta-0309-non-reasoning` |
| xAI | `xai/grok-4.20-beta-0309-reasoning` |
| xAI | `xai/grok-4.20-multi-agent-beta-0309` |
| xAI | `xai/grok-4.3` |
| xAI | `xai/grok-4.3-latest` |
| xAI | `xai/grok-beta` |
| xAI | `xai/grok-code-fast` |
| xAI | `xai/grok-code-fast-1` |
| xAI | `xai/grok-code-fast-1-0825` |
| xAI | `xai/grok-vision-beta` |
| Xiaomi | `mimo-v2-flash` |
| Xiaomi | `mimo-v2-omni` |
| Xiaomi | `mimo-v2-pro` |
| Xiaomi | `mimo-v2.5` |
| Xiaomi | `mimo-v2.5-pro` |
| Zhipu AI / Z.ai | `glm-4.5` |
| Zhipu AI / Z.ai | `glm-4.5-air` |
| Zhipu AI / Z.ai | `glm-4.5-flash` |
| Zhipu AI / Z.ai | `glm-4.5v` |
| Zhipu AI / Z.ai | `glm-4.6` |
| Zhipu AI / Z.ai | `glm-4.6v` |
| Zhipu AI / Z.ai | `glm-4.7` |
| Zhipu AI / Z.ai | `glm-4.7-flash` |
| Zhipu AI / Z.ai | `glm-4.7-flashx` |
| Zhipu AI / Z.ai | `glm-5` |
| Zhipu AI / Z.ai | `glm-5-turbo` |
| Zhipu AI / Z.ai | `glm-5.1` |
| Zhipu AI / Z.ai | `glm-5v-turbo` |

## Providers with no model rows in this Core registry snapshot

These are still valid public catalog identities. Their current public pages and model inventories come from the platform's frozen OpenRouter/Bedrock reconciliation or historical catalog, not from this older Core capability snapshot.

| Provider | Provider key |
| --- | --- |
| Cursor | `cursor` |
| 01.AI | `01-ai` |
| Baidu | `baidu` |
| Huawei | `huawei` |
| iFlytek | `iflytek` |
| Kuaishou | `kuaishou` |
| Meituan | `meituan` |
| OpenBMB / ModelBest | `openbmb` |
| SenseTime | `sensetime` |
| Shanghai AI Lab | `shanghai-ai-lab` |
| Adept AI | `adept-ai` |
| AI71 | `ai71` |
| Aion Labs | `aion-labs` |
| Aleph Alpha | `aleph-alpha` |
| Allen Institute for AI, AI2 | `ai2` |
| Anthracite Org | `anthracite-org` |
| Apple | `apple` |
| Arcee AI | `arcee-ai` |
| BAAI, Beijing Academy of AI | `baai` |
| Baichuan AI | `baichuan-ai` |
| BigCode / ServiceNow / Hugging Face | `bigcode` |
| BigScience / Hugging Face community | `bigscience` |
| Character.AI | `character-ai` |
| Cognitive Computations | `cognitivecomputations` |
| Contextual AI | `contextual-ai` |
| DeepCogito | `deepcogito` |
| EleutherAI | `eleutherai` |
| Essential AI | `essential-ai` |
| Gryphe | `gryphe` |
| IBM Granite | `ibm-granite` |
| InclusionAI | `inclusionai` |
| Inflection AI | `inflection-ai` |
| Kakao | `kakao` |
| Krutrim | `krutrim` |
| KwaiPilot | `kwaipilot` |
| LG AI Research | `lg` |
| LightOn | `lighton` |
| Liquid AI | `liquid-ai` |
| Mancer | `mancer` |
| Naver | `naver` |
| Nex AGI | `nex-agi` |
| Nous Research | `nous-research` |
| Perceptron | `perceptron` |
| Reka AI | `reka-ai` |
| Relace | `relace` |
| Sakana AI | `sakana` |
| Salesforce AI Research | `salesforce` |
| Samsung Research | `samsung-research` |
| Sao10K | `sao10k` |
| SDAIA / IBM / Saudi ecosystem | `sdaia` |
| SK Telecom | `sk-telecom` |
| Technology Innovation Institute, UAE | `tii` |
| TheDrummer | `thedrummer` |
| Thinking Machines | `thinkingmachines` |
| Undi95 | `undi95` |
| Writer | `writer` |
| XVERSE AI | `xverse-ai` |
| Yandex | `yandex` |
