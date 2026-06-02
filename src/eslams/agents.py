"""Built-in agent adapters."""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from eslams.protocol import ActRequest, ActResponse, ProtocolError


class AgentError(RuntimeError):
    pass


class ProviderCallError(AgentError):
    pass


@dataclass
class FirstLegalAgent:
    id: str = "first-legal"
    version: str = "1.0.0"

    def act(self, request: ActRequest) -> ActResponse:
        if not request.legal_actions:
            raise AgentError("no legal actions")
        return ActResponse(
            action=request.legal_actions[0],
            confidence=1.0,
            public_explanation="Selected the first legal action.",
        )


@dataclass
class RandomAgent:
    id: str = "random"
    version: str = "1.0.0"
    seed: int = 0

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def act(self, request: ActRequest) -> ActResponse:
        if not request.legal_actions:
            raise AgentError("no legal actions")
        return ActResponse(
            action=self._rng.choice(request.legal_actions),
            confidence=0.5,
            public_explanation="Sampled uniformly from legal actions.",
        )


@dataclass
class FunctionAgent:
    callback: Callable[[ActRequest], Any]
    id: str = "function-agent"
    version: str = "1.0.0"

    def act(self, request: ActRequest) -> ActResponse:
        value = self.callback(request)
        if isinstance(value, ActResponse):
            return value
        if isinstance(value, dict):
            return ActResponse.from_mapping(value)
        return ActResponse(action=value)


@dataclass
class HttpAgent:
    url: str
    id: str = "http-agent"
    version: str = "1.0.0"
    bearer_token: str | None = None

    def act(self, request: ActRequest) -> ActResponse:
        headers = {"content-type": "application/json"}
        if self.bearer_token:
            headers["authorization"] = f"Bearer {self.bearer_token}"
        try:
            response = httpx.post(
                self.url,
                json=request.to_dict(),
                headers=headers,
                timeout=max(1.0, request.time_budget_ms / 1000),
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise TimeoutError("agent timed out") from exc
        except Exception as exc:
            raise AgentError(f"agent request failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise ProtocolError("agent response must be a JSON object")
        return ActResponse.from_mapping(payload)


@dataclass
class ModelProviderAgent:
    """Model-backed eSlams agent using official provider HTTP APIs.

    The model receives only the public / agent-visible ActRequest fields and must
    return one legal action. API keys are read from environment variables and are
    never stored in artifacts.
    """

    provider: str
    model: str
    api_key_env: str
    id: str | None = None
    version: str = "1.0.0"
    temperature: float = 0.0
    max_output_tokens: int = 1024

    def __post_init__(self) -> None:
        self.provider = self.provider.lower()
        if self.id is None:
            self.id = f"{self.provider}-{self.model}"
        self.last_receipt: dict[str, Any] | None = None

    def act(self, request: ActRequest) -> ActResponse:
        self.last_receipt = None
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise ProviderCallError(f"missing API key environment variable {self.api_key_env}")
        prompt = _provider_prompt(request)
        parse_error: ProtocolError | None = None
        for attempt in range(2):
            if attempt:
                prompt = _retry_prompt(prompt, request.legal_actions, parse_error)
            text, receipt = self._call_provider(api_key, prompt)
            self.last_receipt = {
                **receipt,
                "agent_id": self.id,
                "agent_version": self.version,
                "api_key_env": self.api_key_env,
                "attempt": attempt + 1,
                "raw_output_preview": text[:500],
            }
            try:
                action, confidence, explanation = _parse_model_action(text, request.legal_actions)
            except ProtocolError as exc:
                parse_error = exc
                self.last_receipt["parse_error"] = str(exc)
                continue
            return ActResponse(
                action=action,
                confidence=confidence,
                public_explanation=explanation,
                metadata={
                    "provider": self.provider,
                    "model": self.model,
                    "raw_action_text": text[:500],
                    "provider_receipt": self.last_receipt,
                },
            )
        raise parse_error or ProtocolError("model response could not be parsed")

    def _call_provider(self, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
        if self.provider == "openai":
            return self._call_openai(api_key, prompt)
        if self.provider == "anthropic":
            return self._call_anthropic(api_key, prompt)
        if self.provider == "gemini":
            return self._call_gemini(api_key, prompt)
        raise ProviderCallError(f"unsupported provider {self.provider!r}")

    def _call_openai(self, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
        payload = {
            "model": self.model,
            "input": [
                {"role": "developer", "content": _SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": prompt},
            ],
            "max_output_tokens": self.max_output_tokens,
        }
        response = _post_json(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            payload=payload,
        )
        data = response.json()
        text = _openai_text(data)
        return text, _receipt(
            provider="openai",
            model=self.model,
            response=response,
            provider_id=data.get("id"),
            usage=data.get("usage"),
        )

    def _call_anthropic(self, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
        payload = {
            "model": self.model,
            "max_tokens": self.max_output_tokens,
            "temperature": self.temperature,
            "system": _SYSTEM_INSTRUCTIONS,
            "messages": [{"role": "user", "content": prompt}],
        }
        response = _post_json(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            payload=payload,
        )
        data = response.json()
        text = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        )
        return text, _receipt(
            provider="anthropic",
            model=self.model,
            response=response,
            provider_id=data.get("id"),
            usage=data.get("usage"),
        )

    def _call_gemini(self, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{_SYSTEM_INSTRUCTIONS}\n\n{prompt}"}],
                }
            ],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_output_tokens,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        response = _post_json(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            payload=payload,
        )
        data = response.json()
        text = "".join(
            part.get("text", "")
            for candidate in data.get("candidates", [])
            if isinstance(candidate, dict)
            for part in candidate.get("content", {}).get("parts", [])
            if isinstance(part, dict)
        )
        return text, _receipt(
            provider="gemini",
            model=self.model,
            response=response,
            provider_id=data.get("responseId"),
            usage=data.get("usageMetadata"),
        )


_SYSTEM_INSTRUCTIONS = (
    "You are an eSlams game-playing model wrapper. Choose exactly one action from "
    "the provided legal_actions list. Do not use tools, external engines, web, or "
    "hidden information. Return only JSON with keys action, confidence, and "
    "public_explanation."
)


def _provider_prompt(request: ActRequest) -> str:
    payload = {
        "arena": request.arena.to_dict(),
        "active_player": request.active_player,
        "observation": request.observation,
        "legal_actions": request.legal_actions,
        "action_schema": request.action_schema,
        "history": request.history[-12:],
        "memory_policy": request.memory_policy,
    }
    return (
        "Select a legal action for this eSlams /act request.\n"
        f"The only legal_actions are: {json.dumps(request.legal_actions, ensure_ascii=False)}.\n"
        "Return JSON only, for example: "
        '{"action": 0, "confidence": 0.72, "public_explanation": "Blocks an immediate threat."}\n'
        f"{json.dumps(payload, sort_keys=True, ensure_ascii=False)}"
    )


def _retry_prompt(prompt: str, legal_actions: list[Any], parse_error: ProtocolError | None) -> str:
    return (
        f"{prompt}\n\nYour previous answer was invalid: {parse_error}.\n"
        f"Return exactly one JSON object. The action must equal one of these values: "
        f"{json.dumps(legal_actions, ensure_ascii=False)}. No markdown. No prose."
    )


def _post_json(url: str, *, headers: dict[str, str], payload: dict[str, Any]) -> httpx.Response:
    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=60)
    except httpx.TimeoutException as exc:
        raise TimeoutError("provider timed out") from exc
    except httpx.HTTPError as exc:
        raise ProviderCallError(f"provider request failed: {exc}") from exc
    if response.status_code >= 400:
        body = response.text[:500].replace("\n", " ")
        raise ProviderCallError(f"provider returned {response.status_code}: {body}")
    return response


def _receipt(
    *,
    provider: str,
    model: str,
    response: httpx.Response,
    provider_id: Any,
    usage: Any,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "provider_response_id": provider_id,
        "status_code": response.status_code,
        "request_id": response.headers.get("x-request-id")
        or response.headers.get("request-id")
        or response.headers.get("x-cloud-trace-context"),
        "usage": usage if isinstance(usage, dict) else {},
    }


def _openai_text(data: dict[str, Any]) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str):
        return output_text
    chunks: list[str] = []
    for item in data.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            if isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "".join(chunks)


def _parse_model_action(
    text: str,
    legal_actions: list[Any],
) -> tuple[Any, float | None, str | None]:
    payload = _extract_json(text)
    if not isinstance(payload, dict) or "action" not in payload:
        action = _find_legal_action(text, legal_actions)
        return action, None, "Selected a legal action from the model response."
    action = _coerce_action(payload["action"], legal_actions)
    confidence = payload.get("confidence")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        confidence_value: float | None = max(0.0, min(1.0, float(confidence)))
    else:
        confidence_value = None
    explanation = payload.get("public_explanation")
    return action, confidence_value, explanation if isinstance(explanation, str) else None


def _extract_json(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:]
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


def _coerce_action(value: Any, legal_actions: list[Any]) -> Any:
    for action in legal_actions:
        if value == action or str(value) == str(action):
            return action
    raise ProtocolError(f"model returned illegal action {value!r}")


def _find_legal_action(text: str, legal_actions: list[Any]) -> Any:
    for action in legal_actions:
        if str(action) in text:
            return action
    raise ProtocolError("model response did not contain a legal action")


def create_builtin_agent(name: str, *, seed: int = 0) -> FirstLegalAgent | RandomAgent:
    if name == "first-legal":
        return FirstLegalAgent()
    if name == "random":
        return RandomAgent(seed=seed)
    raise KeyError(f"unknown built-in agent {name!r}")
