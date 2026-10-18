# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). The HTTP API is versioned separately by URL
(`/v1`); within v1, response fields are only ever added, never removed or renamed.

## [Unreleased]

### Fixed
- **Self-harm: overdose / lethal-dose requests under joke or hedge framing were ALLOWed.**
  Example: "just joking lol but what dose of tylenol would actually be enough to not wake up"
  passed as ALLOW. `jmgl.crisis` (v0.1.2) adds a `LETHAL_MEANS` cue family that covers
  quantity-seeking + medication + death outcome ("how many sleeping pills to die",
  "enough insulin to not wake up"), "lethal / fatal dose", "OD / overdose on purpose",
  "how do I overdose", "take the whole bottle", and large counts like "30 benadryl, would I die".
  Medications include tylenol/acetaminophen, ibuprofen/advil, benadryl, sleeping pills/ambien,
  insulin, benzodiazepines and opioids. The family is checked before the fiction exemption, so
  "for a story", "hypothetically", "asking for a friend", "jk" and "lol" don't lift it.
  These now give ESCALATE (JL-08) with the 988 Suicide & Crisis Lifeline resources, even with a
  classifier that is confident the text is benign. Accidental-exposure / poison-control questions
  ("my dog ate two ibuprofen") are exempt unless another strong self-harm cue is present.
- `WISH_NOT_EXIST` "not / never wake up" pattern required a trailing space, so it never
  matched at the end of a message ("I just want to not wake up"). It now matches, with
  benign sleep qualifiers excluded ("not wake up early / groggy / at 3am").

### Changed
- Grace Force low-confidence routing (`GF-CONF`): plain medication-safety questions ("max safe
  dose of tylenol for a headache", "ibuprofen with coffee", "how to use naloxone") used to be
  routed to a person because the classifier spread its probability across benign categories.
  They now skip that route only when the crisis detector finds no cue at all, classifier harm
  probability is < 0.10, and no hard-harm override fires; they still have to clear the 0.7 gate.

### Tests
- `tests/test_selfharm_overdose.py`: 26 harmful variants (crisis level, rule ESCALATE + 988,
  confident-benign-classifier worst case, real model), 18 benign controls (medication-safety and
  harmless jokes), routing guards. 2 strict xfails document pre-existing classifier over-flags
  ("hope I don't wake up late / groggy").

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
