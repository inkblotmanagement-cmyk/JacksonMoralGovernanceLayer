# Multi-region and global deployment

JMGL's API is **stateless** apart from the audit log, so it scales horizontally and runs in as
many regions as you like. The design choices are about *where audit data lives*.

## Pattern 1: one global endpoint, nearest region (Terraform example)

```
              ┌──────────── Cloud CDN (dashboard static files, cached at the edge)
user ─► global LB ─┤
              └─ /v1 ─► nearest healthy Cloud Run region (us-east1, europe-west1, ...)
                                   └─► audit DB in the primary region
```

* Latency for evaluation is low everywhere (the engine runs in each region, ~5–30 ms).
* Audit writes from distant regions cross regions (adds ~80–120 ms transatlantic) and audit data
  is stored in the primary region. **This is not data residency.**
* Failover is automatic: the LB stops sending traffic to a region whose service is failing.
* For lower write latency you can point each region at its own database (one Cloud SQL per region)
  and aggregate reports offline.

## Pattern 2: one stack per jurisdiction (recommended when residency matters)

```
eu.jmgl.example.org ─► EU stack (europe-west1/4 only) ─► EU database
us.jmgl.example.org ─► US stack (us-east1/us-central1) ─► US database
```

Deploy the Terraform module (or Helm chart, see `deploy/helm/jmgl/values-eu.example.yaml`) once
per jurisdiction with `regions` limited to that jurisdiction. Clients in the EU are configured
with the EU URL. Each stack has its own keys, retention and `JMGL_REGION` label. This keeps
personal data (if any is logged) in the jurisdiction where it was collected.

## CDN for the dashboard

The dashboard is static (HTML/JS/CSS ~250 KB). Hashed assets under `/assets/` are cached for a
year (`immutable`); `index.html` and `config.js` are `no-cache` so new releases appear
immediately. Any CDN works (Cloud CDN, CloudFront, Cloudflare, Render/Netlify/Vercel static
hosting). `config.js` sets `apiBaseUrl`; leave it empty when the CDN and API share a hostname
(as in the Terraform LB) or set it to the API URL and add the dashboard origin to
`JMGL_CORS_ORIGINS`.

## Rate limiting across regions

In-process limits apply per replica. For a global limit use the edge (Cloud Armor in the
Terraform example) and/or a Redis per region (`JMGL_RATE_LIMIT_REDIS_URL`).

## Private database networking (hardening option)

The Terraform example reaches Cloud SQL through the Cloud SQL connector (IAM + TLS) on an
instance with a public IP but no authorised networks. To remove the public IP, create a VPC,
enable Private Service Access for Cloud SQL, set `ipv4_enabled = false` + `private_network`, and
give each Cloud Run service Direct VPC egress.

## Other clouds

The same shape works elsewhere: AWS (ECS Fargate per region + Global Accelerator or Route 53
latency routing + CloudFront + RDS per region), Azure (Container Apps + Front Door + Azure
Database for PostgreSQL). Only the GCP Terraform example is included and validated.
