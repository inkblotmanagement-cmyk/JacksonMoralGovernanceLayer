# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). The HTTP API is versioned separately by URL
(`/v1`); within v1, response fields are only ever added, never removed or renamed.

## [Unreleased]

## [0.5.0] - 2026-10-07

Engineering hardening for pilots ("production-ready" packaging; see
[docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md) for what that does and does not cover).

### Added
- `jmgl.server`: FastAPI service with `/v1/evaluate`, `/v1/evaluate/batch`, `/v1/laws`,
  `/v1/audit` (cursor pagination, filters, admin-only), `DELETE /v1/audit/{id}` (erasure),
  `/v1/auth/check`, `/healthz`, `/readyz`, `/metrics` (Prometheus), OpenAPI docs.
- Hashed API keys (client/admin roles), per-key and per-IP rate limiting (in-memory or Redis),
  request body / field size limits, strict input validation, CORS allow-list, security headers,
  structured JSON logs with request ids, 12-factor configuration (`JMGL_*` env vars).
- Audit log backends: SQL via SQLAlchemy (SQLite default, PostgreSQL in production), JSONL file,
  or none. HMAC input hashing, opt-in raw text, retention purge, region label.
- Graceful degradation: if the learned classifier cannot load, the API serves rules-only
  verdicts marked `engine.degraded=true` and reports the cause on `/readyz`.
- Reserved `grace_force` response field (null until the Grace Force component ships).
- `jmgl.client.JMGLClient`: zero-dependency Python SDK with retries and typed errors.
- React + TypeScript dashboard (`web/`): evaluate, laws, audit log viewer, API key entry.
- `pyproject.toml` (pip-installable package `jmgl`, extras `model`, `server`, `postgres`,
  `redis`, `dev`; laws and classifier weights bundled in the wheel), `jmgl-server` CLI.
- Multi-stage, non-root Dockerfiles; docker-compose (API + dashboard + PostgreSQL).
- Helm chart (HPA, PDB, probes, resource limits, NetworkPolicy), Terraform example for
  Google Cloud Run multi-region behind a global load balancer with Cloud CDN, Render and
  Fly.io configs.
- CI: lint, type-check, tests, dashboard build, image builds, pip-audit / npm audit / Trivy,
  Helm lint, Terraform validate. No deploy workflow.
- Docs: integration guide, deployment, multi-region, data protection/GDPR, production readiness,
  CONTRIBUTING, SECURITY.

### Changed
- Data files (`spec/laws.json`, `spec/judge_schema.json`, `eval/model/*`) are now located via
  `jmgl._resources` so the package works when installed from a wheel. Override with
  `JMGL_LAWS_PATH`, `JMGL_JUDGE_SCHEMA_PATH`, `JMGL_MODEL_DIR`.
- The classifier caches sentence embeddings per process and loads thread-safely.

### Unchanged
- Engine behaviour: `evaluate_action`, `evaluate_action_ensemble`, the laws, and all 138 gating
  tests are unchanged.

## [0.4.0] - 2026-10-07
- Rules + learned classifier ensemble (88.1% on a template-disjoint held-out split of
  AI-generated data; see `eval/ACCURACY_REPORT.md`).

## [0.3.0]
- Two-stage gate with optional local model judge and fail-closed merge.

## [0.1.1]
- Deterministic rule-and-signal policy evaluator, laws JL-00..JL-10, CLI, JSONL audit.
