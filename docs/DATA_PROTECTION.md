# Data protection, GDPR and residency notes

*Engineering notes, not legal advice. Have counsel review before processing EU/UK personal data.*

## What JMGL processes

* **Request text** (`action`, `context.history`) arrives in memory, is evaluated, and is **not
  stored** by default. Request bodies are never written to logs.
* **Audit records** (default) contain: a decision id, timestamp (UTC), decision, law ids, engine
  mode/versions, a hash of `laws.json`, the classifier confidence, a **hash of the input**, a
  short non-reversible **key id** (first 12 hex chars of the key hash), and the **region** label.
* **Request logs** contain method, route, status, duration, key id and the **client IP** (the IP
  is personal data under GDPR; set your log retention accordingly).
* **Raw text** is stored only if you set `JMGL_AUDIT_LOG_RAW=true`. Requests to an AI system
  often contain names, addresses, health or financial details, so treat raw audit logs as
  potentially *special-category* data.

## Hashes are pseudonymous, not anonymous

A plain SHA-256 of a short sentence can be reversed by guessing. Set `JMGL_AUDIT_HASH_SECRET`
so inputs are hashed with HMAC-SHA256 and a secret only you hold. Hashed records are still
*pseudonymised* personal data if you can link them back to a person.

## Controls available

| Need | Setting / endpoint |
|---|---|
| Data minimisation | `JMGL_AUDIT_LOG_RAW=false` (default), `JMGL_AUDIT_HASH_SECRET` |
| Storage limitation / retention | `JMGL_AUDIT_RETENTION_DAYS` (default 90, `0` = keep forever); purge runs every `JMGL_AUDIT_PURGE_INTERVAL_MINUTES` and via `jmgl-server purge-audit` |
| Right to erasure | `DELETE /v1/audit/{id}` (admin key); the response `id` is what a client should keep to locate a record |
| Access control | Audit read/delete need an **admin** key; client keys can only evaluate |
| Residency | Deploy one stack per jurisdiction ([MULTI_REGION.md](MULTI_REGION.md)); every record carries `region` |
| Security of processing | TLS at the edge, non-root containers, hashed API keys, encrypted Cloud SQL, backups with PITR |
| Accountability | Each record includes engine version and the laws hash, so decisions can be explained later |

## Checklist before a pilot with personal data

- [ ] Decide controller/processor roles with the pilot customer; sign a DPA.
- [ ] Record the processing (purpose: AI safety/governance decisions; lawful basis, often
      legitimate interests or contract) and run a DPIA if decisions affect people significantly.
- [ ] Keep `JMGL_AUDIT_LOG_RAW=false` unless there is a documented need; if enabled, shorten
      retention and restrict admin keys.
- [ ] Pick regions that match where data subjects are (EU data → EU stack).
- [ ] Set log retention in your platform (Cloud Logging, etc.) for request logs containing IPs.
- [ ] Note automated decision-making: JMGL verdicts that significantly affect a person should
      have human review (ESCALATE/MODIFY already route to people).
- [ ] Update the privacy notice of the product that uses JMGL.
