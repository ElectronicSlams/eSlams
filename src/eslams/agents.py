"""Built-in agent adapters."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from eslams.protocol import ActRequest, ActResponse, ProtocolError


class AgentError(RuntimeError):
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


def create_builtin_agent(name: str, *, seed: int = 0) -> FirstLegalAgent | RandomAgent:
    if name == "first-legal":
        return FirstLegalAgent()
    if name == "random":
        return RandomAgent(seed=seed)
    raise KeyError(f"unknown built-in agent {name!r}")
