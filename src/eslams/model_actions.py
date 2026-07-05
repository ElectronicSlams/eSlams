"""Shared model-action parsing, schema, and retry contracts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from eslams.action_descriptors import action_token
from eslams.protocol import ProtocolError

INVALID_ACTION_CODES: tuple[str, ...] = (
    "invalid_json",
    "schema_mismatch",
    "unknown_action_id",
    "illegal_action_for_state",
    "action_valid_but_wrong_actor",
    "empty_output",
    "timeout_before_action",
    "provider_error",
)


class InvalidModelAction(ProtocolError):
    """Raised when a model output cannot be mapped to a legal Core action."""

    def __init__(self, code: str, detail: str) -> None:
        if code not in INVALID_ACTION_CODES:
            code = "schema_mismatch"
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True)
class ParsedModelAction:
    action: Any
    action_id: str
    confidence: float | None
    public_explanation: str | None


def parse_model_action(text: str, legal_actions: list[Any]) -> ParsedModelAction:
    """Parse a provider response into one legal action using the shared policy."""

    if not text.strip():
        raise InvalidModelAction("empty_output", "model output was empty")
    token_to_action = {action_token(action): action for action in legal_actions}
    payload = extract_json(text)
    if not isinstance(payload, dict):
        raise InvalidModelAction(
            "invalid_json",
            "model response must be a JSON object with action",
        )

    action_value = _action_value(payload)
    if action_value is _MISSING:
        raise InvalidModelAction("schema_mismatch", "response.action is required")

    action = coerce_action(action_value, legal_actions, token_to_action)
    confidence = payload.get("confidence")
    confidence_value: float | None
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        confidence_value = max(0.0, min(1.0, float(confidence)))
    else:
        confidence_value = None
    explanation = payload.get("public_explanation")
    return ParsedModelAction(
        action=action,
        action_id=action_token(action),
        confidence=confidence_value,
        public_explanation=explanation if isinstance(explanation, str) else None,
    )


def extract_json(text: str) -> Any:
    stripped = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end > start:
            with_json = stripped[start : end + 1]
            try:
                return json.loads(with_json)
            except json.JSONDecodeError:
                return None
    return None


def coerce_action(
    value: Any,
    legal_actions: list[Any],
    token_to_action: dict[str, Any] | None = None,
) -> Any:
    tokens = token_to_action or {action_token(action): action for action in legal_actions}
    if isinstance(value, str) and value in tokens:
        return tokens[value]
    for action in legal_actions:
        if value == action or str(value) == str(action):
            return action
    if isinstance(value, str):
        raise InvalidModelAction("unknown_action_id", f"unknown action id {value!r}")
    raise InvalidModelAction("illegal_action_for_state", f"model returned illegal action {value!r}")


def find_legal_action(text: str, legal_actions: list[Any]) -> Any:
    raise InvalidModelAction(
        "invalid_json",
        "model response must be a JSON object with action",
    )


def invalid_action_retry_prompt(
    prompt: str,
    legal_actions: list[Any],
    error: Exception | None,
) -> str:
    detail = str(error) if error is not None else "response was invalid"
    legal_ids = [action_token(action) for action in legal_actions]
    return (
        f"{prompt}\n\nYour previous answer was invalid: {detail}.\n"
        "Return exactly one JSON object with action first. Use either "
        '{"action": {"action_id": "..."} } or the legacy {"action": ...} form. '
        f"The action_id must be one of: {json.dumps(legal_ids, ensure_ascii=False)}. "
        "No markdown. No prose outside the JSON object."
    )


def action_output_schema(legal_actions: list[Any], *, max_enum: int = 200) -> dict[str, Any]:
    legal_ids = [action_token(action) for action in legal_actions]
    action_id_schema: dict[str, Any] = {"type": "string"}
    if len(legal_ids) <= max_enum:
        action_id_schema["enum"] = legal_ids
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["action", "public_explanation"],
        "properties": {
            "action": {
                "type": "object",
                "additionalProperties": False,
                "required": ["action_id"],
                "properties": {"action_id": action_id_schema},
            },
            "public_explanation": {"type": "string", "maxLength": 500},
        },
    }


def streaming_action_status(buffer: str, legal_actions: list[Any]) -> dict[str, Any]:
    """Return a provider-independent parse status for a streamed response buffer."""

    if not buffer.strip():
        return {"status": "incomplete"}
    ids = {action_token(action) for action in legal_actions}
    match = re.search(r'"action_id"\s*:\s*"([^"]+)"', buffer)
    if match and match.group(1) in ids and _looks_incomplete(buffer):
        return {"status": "action_ready", "action": {"action_id": match.group(1)}}
    try:
        parsed = parse_model_action(buffer, legal_actions)
    except InvalidModelAction as exc:
        if match and match.group(1) in ids:
            return {"status": "action_ready", "action": {"action_id": match.group(1)}}
        if _looks_incomplete(buffer):
            return {"status": "incomplete"}
        return {"status": "invalid", "reason": str(exc), "code": exc.code}
    return {
        "status": "complete",
        "action": {"action_id": parsed.action_id, "payload": parsed.action},
        "explanation": parsed.public_explanation or "",
    }


_MISSING = object()


def _action_value(payload: dict[str, Any]) -> Any:
    if "action_id" in payload:
        return payload["action_id"]
    if "actionId" in payload:
        return payload["actionId"]
    action = payload.get("action", _MISSING)
    if isinstance(action, dict):
        if "action_id" in action:
            return action["action_id"]
        if "actionId" in action:
            return action["actionId"]
        if "payload" in action:
            return action["payload"]
    return action


def _looks_incomplete(buffer: str) -> bool:
    stripped = buffer.strip()
    if stripped.count("{") > stripped.count("}"):
        return True
    if stripped.count("[") > stripped.count("]"):
        return True
    return stripped.endswith((",", ":", '"'))
