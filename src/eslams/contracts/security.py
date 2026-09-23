"""Security helpers for seed derivation and runner request signing."""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from eslams.hashing import canonical_json, sha256_text

DEFAULT_SIGNATURE_ALGORITHM = "hmac-sha256"
MIN_HMAC_SECRET_LENGTH = 32
RUNNER_REQUEST_SECRET_ENV = "ESLAMS_RUNNER_REQUEST_SECRET"
RUNNER_REQUEST_KEY_ID_ENV = "ESLAMS_RUNNER_REQUEST_KEY_ID"
RUNNER_REQUEST_SECRET_PREVIOUS_ENV = "ESLAMS_RUNNER_REQUEST_SECRET_PREVIOUS"
RUNNER_REQUEST_KEY_ID_PREVIOUS_ENV = "ESLAMS_RUNNER_REQUEST_KEY_ID_PREVIOUS"
RUNNER_REQUEST_ALLOW_UNSIGNED_ENV = "ESLAMS_RUNNER_REQUEST_ALLOW_UNSIGNED"
RUNNER_REQUEST_MAX_AGE_ENV = "ESLAMS_RUNNER_REQUEST_MAX_AGE_SECONDS"
DEFAULT_RUNNER_REQUEST_MAX_AGE_SECONDS = 300
RUNNER_SIGNATURE_HEADER = "X-Eslams-Runner-Signature"
_NON_DEV_ENVIRONMENTS = frozenset({"production", "prod", "staging"})
_MAX_CLOCK_SKEW_SECONDS = 60


class SeedDerivationError(RuntimeError):
    """Raised when deterministic seed derivation cannot proceed safely."""


@dataclass(frozen=True)
class DerivedSeed:
    seed: int
    mode: str
    commitment: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "mode": self.mode,
            "commitment": self.commitment,
        }


def derive_seed(
    *,
    namespace: str,
    public_seed: int | str,
    secret: str | None,
    production: bool,
    allow_development_fallback: bool = False,
) -> DerivedSeed:
    """Derive a deterministic integer seed with fail-closed production semantics."""

    if secret:
        material = f"{namespace}:{public_seed}".encode()
        digest = hmac.new(secret.encode(), material, hashlib.sha256).hexdigest()
        return DerivedSeed(
            seed=_seed_from_digest(digest),
            mode="secret_hmac_sha256",
            commitment=sha256_text(f"{namespace}:{public_seed}:{digest}"),
        )
    if production:
        raise SeedDerivationError("production seed derivation requires a secret")
    if not allow_development_fallback:
        raise SeedDerivationError("development seed fallback must be explicitly enabled")
    digest = hashlib.sha256(f"development:{namespace}:{public_seed}".encode()).hexdigest()
    return DerivedSeed(
        seed=_seed_from_digest(digest),
        mode="development_public_fallback",
        commitment=sha256_text(f"development:{namespace}:{public_seed}:{digest}"),
    )


def signing_payload(
    *,
    method: str,
    path: str,
    body: Any,
    timestamp: str,
    nonce: str,
    request_id: str,
) -> dict[str, str]:
    body_sha256 = hashlib.sha256(canonical_json(body).encode()).hexdigest()
    return {
        "method": method.upper(),
        "path": path,
        "bodySha256": body_sha256,
        "timestamp": timestamp,
        "nonce": nonce,
        "requestId": request_id,
    }


def signing_string(payload: dict[str, str]) -> str:
    return "\n".join(
        [
            payload["method"],
            payload["path"],
            payload["bodySha256"],
            payload["timestamp"],
            payload["nonce"],
            payload["requestId"],
        ]
    )


def sign_runner_request(
    *,
    secret: str,
    method: str,
    path: str,
    body: Any,
    timestamp: str,
    nonce: str,
    request_id: str,
    key_id: str,
) -> dict[str, str]:
    payload = signing_payload(
        method=method,
        path=path,
        body=body,
        timestamp=timestamp,
        nonce=nonce,
        request_id=request_id,
    )
    signature = hmac.new(
        secret.encode(),
        signing_string(payload).encode(),
        hashlib.sha256,
    ).hexdigest()
    return {
        "algorithm": DEFAULT_SIGNATURE_ALGORITHM,
        "keyId": key_id,
        "signature": signature,
        **payload,
    }


def verify_runner_request_signature(
    *,
    secret: str,
    signature_payload: dict[str, str],
) -> bool:
    required = {
        "algorithm",
        "keyId",
        "signature",
        "method",
        "path",
        "bodySha256",
        "timestamp",
        "nonce",
        "requestId",
    }
    if not required.issubset(signature_payload):
        return False
    if signature_payload["algorithm"] != DEFAULT_SIGNATURE_ALGORITHM:
        return False
    expected = hmac.new(
        secret.encode(),
        signing_string(signature_payload).encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_payload["signature"])


def _seed_from_digest(digest: str) -> int:
    return int(digest[:16], 16) % (2**31 - 1)


class RunnerAuthConfigError(RuntimeError):
    """Raised when runner HTTP authentication is missing or misconfigured."""


class RunnerRequestAuthError(Exception):
    """Raised when a runner HTTP request fails authentication."""

    def __init__(self, code: str = "invalid") -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class RunnerAuthConfig:
    """Resolved runner HTTP authentication configuration.

    ``mode="signed"`` verifies HMAC request signatures.
    ``mode="unsigned_dev"`` is an explicit local opt-in with no built-in secret.
    """

    mode: str
    secrets_by_key_id: dict[str, str]
    max_age_seconds: int


def is_non_dev_environment() -> bool:
    """Return whether ``ESLAMS_ENV`` selects a shared or production environment."""

    return os.getenv("ESLAMS_ENV", "").strip().lower() in _NON_DEV_ENVIRONMENTS


def parse_utc_timestamp(value: str) -> datetime:
    """Parse an RFC 3339 UTC timestamp emitted by Core signing helpers."""

    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def load_runner_auth_config() -> RunnerAuthConfig:
    """Load runner HTTP auth from the environment.

    There is no built-in shared secret. Operators set
    ``ESLAMS_RUNNER_REQUEST_SECRET`` and ``ESLAMS_RUNNER_REQUEST_KEY_ID``.
    During rotation, keep the previous secret and key id in
    ``ESLAMS_RUNNER_REQUEST_SECRET_PREVIOUS`` and
    ``ESLAMS_RUNNER_REQUEST_KEY_ID_PREVIOUS`` until every caller has switched,
    then remove the previous pair and restart. Do not log either secret.
    """

    max_age = _positive_seconds(
        RUNNER_REQUEST_MAX_AGE_ENV,
        DEFAULT_RUNNER_REQUEST_MAX_AGE_SECONDS,
    )
    secret = os.getenv(RUNNER_REQUEST_SECRET_ENV)
    previous = os.getenv(RUNNER_REQUEST_SECRET_PREVIOUS_ENV)
    if secret is None or secret == "":
        if previous not in (None, ""):
            raise RunnerAuthConfigError(f"{RUNNER_REQUEST_SECRET_ENV} is required")
        allow_unsigned = os.getenv(RUNNER_REQUEST_ALLOW_UNSIGNED_ENV) == "1"
        if allow_unsigned and not is_non_dev_environment():
            return RunnerAuthConfig(
                mode="unsigned_dev",
                secrets_by_key_id={},
                max_age_seconds=max_age,
            )
        raise RunnerAuthConfigError(f"{RUNNER_REQUEST_SECRET_ENV} is required")

    current_secret = _require_hmac_secret(secret, RUNNER_REQUEST_SECRET_ENV)
    current_key_id = _require_key_id(
        os.getenv(RUNNER_REQUEST_KEY_ID_ENV),
        RUNNER_REQUEST_KEY_ID_ENV,
    )
    secrets = {current_key_id: current_secret}
    if previous not in (None, ""):
        previous_secret = _require_hmac_secret(previous, RUNNER_REQUEST_SECRET_PREVIOUS_ENV)
        previous_key_id = _require_key_id(
            os.getenv(RUNNER_REQUEST_KEY_ID_PREVIOUS_ENV),
            RUNNER_REQUEST_KEY_ID_PREVIOUS_ENV,
        )
        if previous_key_id == current_key_id or previous_secret == current_secret:
            raise RunnerAuthConfigError(f"{RUNNER_REQUEST_SECRET_PREVIOUS_ENV} is misconfigured")
        secrets[previous_key_id] = previous_secret
    return RunnerAuthConfig(mode="signed", secrets_by_key_id=secrets, max_age_seconds=max_age)


def verify_signed_runner_request(
    *,
    config: RunnerAuthConfig,
    method: str,
    path: str,
    body: Any,
    signature_payload: dict[str, Any],
    seen_nonces: dict[str, float],
    now: float | None = None,
) -> None:
    """Authorize one runner HTTP request. Raises ``RunnerRequestAuthError`` on failure."""

    if config.mode != "signed":
        raise RunnerRequestAuthError("unconfigured")
    normalized = {
        str(key): str(value) for key, value in signature_payload.items() if value is not None
    }
    required = {
        "algorithm",
        "keyId",
        "signature",
        "method",
        "path",
        "bodySha256",
        "timestamp",
        "nonce",
        "requestId",
    }
    if not required.issubset(normalized):
        raise RunnerRequestAuthError()
    if normalized["method"] != method.upper() or normalized["path"] != path:
        raise RunnerRequestAuthError()
    if not normalized["nonce"] or len(normalized["nonce"]) > 256:
        raise RunnerRequestAuthError()
    body_sha = hashlib.sha256(canonical_json(body).encode()).hexdigest()
    if not hmac.compare_digest(body_sha, normalized["bodySha256"]):
        raise RunnerRequestAuthError()
    secret = config.secrets_by_key_id.get(normalized["keyId"])
    if secret is None or not verify_runner_request_signature(
        secret=secret,
        signature_payload=normalized,
    ):
        raise RunnerRequestAuthError()
    try:
        signed_at = parse_utc_timestamp(normalized["timestamp"])
    except ValueError as exc:
        raise RunnerRequestAuthError() from exc
    current = (
        datetime.fromtimestamp(now, timezone.utc) if now is not None else datetime.now(timezone.utc)
    )
    age = (current - signed_at).total_seconds()
    if age > config.max_age_seconds or age < -_MAX_CLOCK_SKEW_SECONDS:
        raise RunnerRequestAuthError()
    current_epoch = current.timestamp()
    expired = [nonce for nonce, expiry in seen_nonces.items() if expiry < current_epoch]
    for nonce in expired:
        del seen_nonces[nonce]
    if normalized["nonce"] in seen_nonces:
        raise RunnerRequestAuthError()
    seen_nonces[normalized["nonce"]] = current_epoch + config.max_age_seconds


def _require_hmac_secret(value: str | None, label: str) -> str:
    if value is None or value == "":
        raise RunnerAuthConfigError(f"{label} is required")
    stripped = value.strip()
    if stripped != value or len(stripped) < MIN_HMAC_SECRET_LENGTH:
        raise RunnerAuthConfigError(f"{label} is misconfigured")
    return stripped


def _require_key_id(value: str | None, label: str) -> str:
    if value is None:
        raise RunnerAuthConfigError(f"{label} is required")
    stripped = value.strip()
    if not stripped or stripped != value or len(stripped) > 128:
        raise RunnerAuthConfigError(f"{label} is misconfigured")
    if any(char.isspace() for char in stripped):
        raise RunnerAuthConfigError(f"{label} is misconfigured")
    return stripped


def _positive_seconds(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise RunnerAuthConfigError(f"{name} is misconfigured") from exc
    if parsed <= 0:
        raise RunnerAuthConfigError(f"{name} is misconfigured")
    return parsed
