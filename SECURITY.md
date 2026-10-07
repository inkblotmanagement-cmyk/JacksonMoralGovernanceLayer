# Security policy

## Supported versions

| Version | Supported |
|---|---|
| 0.5.x | Yes |
| < 0.5 | No (library-only releases; upgrade) |

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Use GitHub's private
vulnerability reporting (repository → *Security* → *Report a vulnerability*). If that is not
available, contact the maintainer (Terrance Jackson, Mindful Oracle LLC) via X
[@Terranc34045610](https://x.com/Terranc34045610) to arrange a private channel.

Include: affected version/commit, a description, reproduction steps, and impact. We aim to
acknowledge within 3 business days and to agree on a fix/disclosure timeline with you. This is
a small project without a bug bounty.

## Scope

In scope: the API (`src/jmgl/server`), SDK, dashboard, Dockerfiles, Helm chart and Terraform
example. **Bypasses of the moral rules** (prompts that get harmful requests ALLOWed) are
valuable but expected for a pilot-stage engine; please report them as regular issues or test
cases unless they reveal a software vulnerability.

## Security design summary

* API keys are stored only as SHA-256 hashes; comparison is constant-time; client and admin roles.
* Production mode refuses to start without keys, with the sample keys, with auth disabled, or
  with wildcard CORS.
* Request size limits, strict schema validation, per-key/IP rate limits.
* Request bodies are never logged; audit stores input hashes (HMAC with a secret if configured).
* Containers run as non-root, support read-only root filesystems, and include no shell tools
  beyond the base image; images are scanned with Trivy in CI.
* CI runs with read-only permissions and no secrets; there is no automated deploy.

## Operator responsibilities

Rotate keys if exposed (remove the hash, restart), keep images updated, restrict `/metrics`
and `/docs` to internal networks, enable TLS at the edge, and follow
[docs/DATA_PROTECTION.md](docs/DATA_PROTECTION.md).
