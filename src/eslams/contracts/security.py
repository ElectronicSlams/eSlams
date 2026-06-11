"""Security helpers for seed derivation and runner request signing."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

from eslams.hashing import canonical_json, sha256_text

DEFAULT_SIGNATURE_ALGORITHM = "hmac-sha256"


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
