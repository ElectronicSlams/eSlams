"""Amazon Bedrock Converse adapter metadata."""

PROVIDER_ID = "bedrock"
API_KEY_ENV = "AWS_BEARER_TOKEN_BEDROCK"
DEFAULT_REGION = "us-east-1"
CONVERSE_ENDPOINT_TEMPLATE = (
    "https://bedrock-runtime.{region}.amazonaws.com/model/{model_id}/converse"
)


def converse_endpoint(model_id: str, region: str = DEFAULT_REGION) -> str:
    """Return the literal Bedrock Converse URL.

    Bedrock model IDs intentionally retain their ``:`` version separator.
    Percent-encoding that separator changes AWS routing semantics.
    """

    return CONVERSE_ENDPOINT_TEMPLATE.format(region=region, model_id=model_id)
