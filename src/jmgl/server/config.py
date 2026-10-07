"""12-factor configuration: every setting comes from an environment variable (prefix JMGL_)
or an optional .env file. See .env.example at the repo root for the full, commented list.

No secrets are hard-coded. API keys are configured as SHA-256 *hashes*, never plaintext.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# SHA-256 of the throwaway sample keys in .env.example (jmgl_dev_client_DO_NOT_USE_IN_PRODUCTION
# and jmgl_dev_admin_DO_NOT_USE_IN_PRODUCTION). The server refuses to start in production
# while either is configured.
DEV_SAMPLE_KEY_HASHES = frozenset({
    "fe1a7a99bab63d96dd8b1a94ff45d08204be10f5041d85fa033513b7e9ab0d32",
    "d3ac77c764adb3d99cd20fec6a77004957aabea0767ea4e206463e32cc006e63",
})


def _split_csv(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items = [str(v) for v in value]
    else:
        items = str(value).split(",")
    return [v.strip() for v in items if v.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JMGL_", env_file=".env", env_file_encoding="utf-8",
                                      extra="ignore")

    # --- general
    environment: Literal["development", "test", "production"] = "development"
    region: str = Field(default="local", description="Deployment region label, stored on audit records")
    log_level: str = "INFO"
    log_json: bool = True

    # --- engine
    mode: Literal["ensemble", "rules"] = Field(
        default="ensemble", description="Default engine: rules + learned classifier, or rules only")
    allow_mode_override: bool = Field(default=True, description="Let callers pick mode per request")
    require_model: bool = Field(
        default=False, description="If true, /readyz fails (503) when the classifier cannot load")
    warmup_model: bool = Field(default=True, description="Load the classifier at startup")
    laws_path: Optional[Path] = Field(default=None, description="Custom laws.json (wording/decisions only)")

    # --- auth (comma-separated SHA-256 hex digests of API keys; generate with `jmgl-server gen-key`)
    auth_enabled: bool = True
    client_key_hashes: str = ""
    admin_key_hashes: str = ""
    laws_public: bool = Field(default=True, description="/v1/laws readable without a key")
    metrics_public: bool = Field(default=True, description="/metrics readable without a key (keep it off the public ingress)")

    # --- rate limiting (per API key, or per client IP for public endpoints)
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = Field(default=120, ge=1)
    rate_limit_public_per_minute: int = Field(default=60, ge=1)
    rate_limit_redis_url: str = Field(default="", description="redis://... to share limits across replicas")
    trust_proxy_headers: bool = Field(default=False, description="Use X-Forwarded-For for client IP")

    # --- request limits / validation
    max_body_bytes: int = Field(default=262_144, ge=1024)
    max_action_chars: int = Field(default=8000, ge=1, le=100_000)
    max_history_turns: int = Field(default=20, ge=0, le=200)
    max_batch_items: int = Field(default=50, ge=1, le=1000)

    # --- CORS (comma-separated origins). Empty = no cross-origin browser access.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- audit log
    audit_backend: Literal["sql", "file", "none"] = "sql"
    audit_database_url: str = "sqlite:///./data/jmgl_audit.db"
    audit_file_path: Path = Path("./data/jmgl_audit.jsonl")
    audit_log_raw: bool = Field(default=False, description="Store raw input text (personal data!)")
    audit_hash_secret: str = Field(
        default="", description="If set, input hashes are HMAC-SHA256 with this secret (resists dictionary attacks)")
    audit_retention_days: int = Field(default=90, ge=0, description="0 = keep forever")
    audit_purge_interval_minutes: int = Field(default=60, ge=1)
    audit_auto_create: bool = True
    audit_required: bool = Field(
        default=True, description="If the audit record cannot be written, return 503 instead of a verdict")

    # --- docs
    docs_enabled: bool = True

    @field_validator("log_level")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @field_validator("client_key_hashes", "admin_key_hashes")
    @classmethod
    def _valid_hashes(cls, v: str) -> str:
        cls._hashes(v)  # raises on malformed entries at startup, not on first request
        return v

    @model_validator(mode="after")
    def _production_guards(self) -> Settings:
        if self.environment == "production":
            if not self.auth_enabled:
                raise ValueError("JMGL_AUTH_ENABLED=false is not allowed when JMGL_ENVIRONMENT=production")
            if not (self.client_key_set or self.admin_key_set):
                raise ValueError("Set JMGL_CLIENT_KEY_HASHES and/or JMGL_ADMIN_KEY_HASHES in production")
            if (self.client_key_set | self.admin_key_set) & DEV_SAMPLE_KEY_HASHES:
                raise ValueError("The sample keys from .env.example must not be used in production")
            if "*" in self.cors_origin_list:
                raise ValueError("JMGL_CORS_ORIGINS='*' is not allowed in production")
        return self

    @staticmethod
    def _hashes(raw: str) -> frozenset[str]:
        out = set()
        for h in _split_csv(raw):
            h = h.lower().removeprefix("sha256:")
            if len(h) != 64 or any(c not in "0123456789abcdef" for c in h):
                raise ValueError("API key hashes must be 64-char SHA-256 hex digests (use `jmgl-server gen-key`)")
            out.add(h)
        return frozenset(out)

    @property
    def client_key_set(self) -> frozenset[str]:
        return self._hashes(self.client_key_hashes)

    @property
    def admin_key_set(self) -> frozenset[str]:
        return self._hashes(self.admin_key_hashes)

    @property
    def cors_origin_list(self) -> list[str]:
        return _split_csv(self.cors_origins)


@lru_cache
def get_settings() -> Settings:
    return Settings()
