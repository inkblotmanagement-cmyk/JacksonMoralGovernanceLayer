"""API-key authentication with hashed keys.

Keys are high-entropy random tokens (`jmgl-server gen-key`), so a single SHA-256 is the
appropriate storage hash (as with GitHub/Stripe tokens); a slow password hash adds latency
without adding security for 256-bit random secrets. Only the hashes are configured on the
server; the plaintext key is shown once, to whoever generates it.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

KEY_PREFIX = "jmgl_"
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False,
                              description="JMGL API key (client or admin). `Authorization: Bearer <key>` also works.")


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def generate_key() -> tuple[str, str]:
    """Return (plaintext_key, sha256_hex). Show the key once; configure only the hash."""
    key = KEY_PREFIX + secrets.token_urlsafe(32)
    return key, hash_key(key)


def key_id(key_hash: str) -> str:
    """Short, non-reversible identifier safe to log and store on audit records."""
    return key_hash[:12]


def _in(candidate_hash: str, hashes: frozenset[str]) -> bool:
    ok = False
    for h in hashes:  # constant-time comparison against every configured hash
        ok |= hmac.compare_digest(candidate_hash, h)
    return ok


@dataclass(frozen=True)
class Principal:
    key_id: str
    role: str  # "client" | "admin" | "anonymous"


ANONYMOUS = Principal("anonymous", "anonymous")


def _presented_key(request: Request, header_key: str | None) -> str | None:
    if header_key:
        return header_key.strip()
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def resolve_principal(request: Request, header_key: str | None) -> Principal | None:
    settings = request.app.state.settings
    if not settings.auth_enabled:
        return Principal("auth-disabled", "admin")
    key = _presented_key(request, header_key)
    if not key or len(key) > 512:
        return None
    h = hash_key(key)
    if _in(h, request.app.state.admin_hashes):
        return Principal(key_id(h), "admin")
    if _in(h, request.app.state.client_hashes):
        return Principal(key_id(h), "client")
    return None


def _unauthorized(request: Request, detail: str, code: int = status.HTTP_401_UNAUTHORIZED) -> HTTPException:
    request.app.state.metrics.auth_failures.labels(reason="forbidden" if code == 403 else "invalid").inc()
    return HTTPException(code, detail, headers={"WWW-Authenticate": "ApiKey"})


def require_client(request: Request, header_key: str | None = Depends(api_key_header)) -> Principal:
    p = resolve_principal(request, header_key)
    if p is None:
        raise _unauthorized(request, "Missing or invalid API key")
    request.state.principal = p
    return p


def require_admin(request: Request, header_key: str | None = Depends(api_key_header)) -> Principal:
    p = resolve_principal(request, header_key)
    if p is None:
        raise _unauthorized(request, "Missing or invalid API key")
    if p.role != "admin":
        raise _unauthorized(request, "Admin API key required", status.HTTP_403_FORBIDDEN)
    request.state.principal = p
    return p


def optional_principal(request: Request, header_key: str | None = Depends(api_key_header)) -> Principal:
    p = resolve_principal(request, header_key) if _presented_key(request, header_key) else None
    return p or ANONYMOUS
