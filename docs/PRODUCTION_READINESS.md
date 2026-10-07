# What "production-ready" means for JMGL v0.5.0

Short version: the **software around the engine** is hardened so a pilot customer can run it
reliably and safely. The **moral judgements themselves** are still pilot-stage: they have only
been measured on AI-generated data and have not been independently evaluated or audited.

## Covered (engineering hardening)

| Area | What exists | Where |
|---|---|---|
| API | Versioned `/v1` REST API, OpenAPI docs, strict validation (unknown fields rejected), size limits (body, action, history, batch) | `src/jmgl/server/app.py`, `schemas.py` |
| Auth | API keys stored only as SHA-256 hashes; client vs admin roles; constant-time comparison; production refuses to start without keys, with sample keys, with auth disabled, or with CORS `*` | `security.py`, `config.py` |
| Abuse controls | Per-key and per-IP rate limits (in-memory or Redis-shared), 413 for large bodies, Cloud Armor rate limit in the Terraform example | `ratelimit.py`, `deploy/terraform` |
| Audit | Every verdict stored (PostgreSQL / SQLite / JSONL) with hashed input (HMAC optional), law, mode, key id, region, engine + laws versions; retention purge; erasure endpoint; **fail-closed**: no audit record → no verdict (503), configurable | `audit_store.py` |
| Resilience | Classifier failure → rules-only verdicts flagged `degraded`; DB unreachable at boot → app starts, `/readyz` 503, retries | `service.py`, `audit_store.py` |
| Observability | JSON logs with request ids (bodies never logged), Prometheus metrics (requests, latency, decisions, degraded, auth failures, rate limits, audit errors), liveness/readiness probes | `logging_config.py`, `metrics.py` |
| Packaging | pip-installable wheel with laws + classifier weights bundled; `jmgl-server` CLI; zero-dependency Python SDK; versioning + changelog | `pyproject.toml`, `client.py` |
| Containers | Multi-stage, non-root (uid 10001 / 101), read-only root FS compatible, model pre-bundled (no network at runtime), healthchecks; 0 fixable HIGH/CRITICAL CVEs in Trivy at time of writing | `Dockerfile`, `web/Dockerfile` |
| Deployment | docker-compose, Helm chart (HPA, PDB, probes, limits, NetworkPolicy, zone spreading), Terraform for Cloud Run multi-region + global LB + CDN, Render and Fly configs | `deploy/`, `render.yaml`, `fly.toml` |
| CI | Lint, type-check, ~200 tests (incl. the 138 original gating tests), wheel install test, dashboard lint/test/build, image builds, compose smoke test, pip-audit, npm audit, Trivy, Helm/kubeconform, Terraform validate. No deploy job, no secrets. | `.github/workflows/ci.yml` |

## Not covered yet (needed before relying on JMGL for real decisions)

1. **Real-world evaluation.** Test on real requests from a pilot, labeled by people who did not
   write the rules, including non-English and domain-specific traffic. Publish the results,
   including the benign over-flagging rate, which is currently high (~24–28%).
2. **Independent security review / penetration test** of the API, dashboard, and deployment.
3. **Operations:** an SLA, on-call rotation, incident response runbook, backups restore drill,
   capacity tests at expected load (only a small local smoke load test was run: ~85 req/s on
   8 cores, p95 ~140 ms, one container).
4. **Legal/compliance review:** privacy notice, DPA with customers, records of processing,
   DPIA where required; JMGL alone does not satisfy NIST AI RMF or EU AI Act obligations.
5. **Law governance:** the laws in `spec/laws.json` were approved by Terrance Jackson as working rules on 2026-10-06. A named owner/ethics board should approve changes, and every change should bump
   the laws hash (it already appears on every audit record).
6. **Supply chain hardening (recommended):** pin base images by digest, sign images
   (cosign), publish SBOMs, enable Dependabot/Renovate, protect the main branch.
7. **Database migrations:** the audit table is created automatically; adopt Alembic before the
   schema changes for the first time in production.
8. **Rate limits across replicas:** the default limiter is per process; set
   `JMGL_RATE_LIMIT_REDIS_URL` or rely on edge limits when running several replicas.

## Honest wording for pitches

> "JMGL is an open-source, pilot-stage moral governance engine for AI workflows. It runs as an
> API with authentication, audit logging and monitoring, and it publishes its miss rate. On
> AI-generated test data it caught all but 1.8% of harmful cases, at the cost of sending about a
> quarter of safe requests to human review. We are looking for pilot partners to measure it on
> real traffic."
