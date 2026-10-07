# Deploying JMGL

Nothing in this repository deploys automatically. Each option below needs an account you
create and pay for. Prices are list prices checked in October 2026; verify before buying.

| Option | Best for | Effort | Ballpark cost (quiet pilot) |
|---|---|---|---|
| Docker Compose on one VM | Demos, a single pilot | Low | VM cost only (e.g. a 2 GB VM) |
| Render (`render.yaml`) | "One-click-ish" managed hosting | Low | ~$13/mo: Starter web service $7 + Basic-256mb Postgres $6, static site free tier |
| Fly.io (`fly.toml`) | Simple multi-region (e.g. Atlanta + Amsterdam) | Low–medium | ~$6.70/mo per always-on 1 GB machine in US regions (more in EU/Asia) + a Postgres you choose (Fly Managed Postgres Basic starts at $38/mo) |
| Google Cloud Run + global LB (`deploy/terraform/gcp-cloud-run`) | Global, autoscaling, CDN | Medium | ~$35–60/mo idle for 2 regions: LB forwarding rules ≈ $18, Cloud SQL db-f1-micro ≈ $9–10 + storage, Cloud Armor ≈ $7 + $0.75/M requests, Cloud Run mostly in free tier at low traffic (more with `min_instances ≥ 1`) |
| Kubernetes (`deploy/helm/jmgl`) | Teams already running K8s (GKE/EKS/AKS) | Medium–high | Cluster cost (often $70+/mo for a managed control plane + nodes) |

Sources: render.com/pricing, fly.io/pricing (Oct 1 2026 update), cloud.google.com/load-balancing/pricing,
cloud.google.com/sql/pricing, cloud.google.com/armor/pricing.

Plus a **domain name** (~$10–20/year) for HTTPS on your own hostname.

## Before any deployment

1. Generate keys: `jmgl-server gen-key` (once per client app, plus one admin key). Store the
   plaintext keys in a password/secret manager; configure only the hashes.
2. Set `JMGL_AUDIT_HASH_SECRET` to a long random value (e.g. `python -c "import secrets;print(secrets.token_urlsafe(48))"`).
3. Decide retention (`JMGL_AUDIT_RETENTION_DAYS`, default 90) and whether raw text is logged
   (`JMGL_AUDIT_LOG_RAW`, default **false**). Read [DATA_PROTECTION.md](DATA_PROTECTION.md).
4. Build and push images to a registry you control (GHCR, Artifact Registry, ECR, Docker Hub):
   ```bash
   docker build -t REGISTRY/jmgl-api:0.5.0 .
   docker build -t REGISTRY/jmgl-web:0.5.0 web
   docker push REGISTRY/jmgl-api:0.5.0 && docker push REGISTRY/jmgl-web:0.5.0
   ```

## Docker Compose (single host)

`docker compose up -d --build` starts PostgreSQL, the API (port 8000) and the dashboard
(port 8080, which also proxies `/v1` to the API). For a real host: put a TLS reverse proxy
(Caddy, nginx, a cloud LB) in front of port 8080, set `JMGL_ENVIRONMENT=production`, replace the
sample key hashes, set a strong `POSTGRES_PASSWORD`, and remove the `8000:8000` port mapping if
the API should only be reached through the dashboard host.

## Render

Dashboard → **New → Blueprint** → select the repo. Render reads `render.yaml`, asks for the
`sync: false` values (key hashes, CORS origin), creates the API, the static dashboard (with
rewrites so the dashboard calls `/v1` on the same origin) and PostgreSQL. `autoDeploy` is off;
deploy manually. If you rename the API service, update the rewrite destinations.

## Fly.io

See the comments at the top of `fly.toml`: `fly launch --no-deploy --copy-config`,
`fly secrets set ...`, `fly deploy`, then `fly scale count 2 --region atl,ams` for two regions.
Host `web/dist` on any static host/CDN with `config.js` pointing at the API URL (and add that
origin to `JMGL_CORS_ORIGINS`), or deploy `web/Dockerfile` as a second Fly app with
`JMGL_API_UPSTREAM=https://<api-app>.fly.dev`.

## Google Cloud Run (Terraform, multi-region)

```bash
cd deploy/terraform/gcp-cloud-run
cp terraform.tfvars.example terraform.tfvars      # edit project, regions, image, domain
terraform init && terraform plan                   # review; apply only when you're ready
terraform apply
# populate secrets (values never go into Terraform state):
printf '%s' "<client-hash>" | gcloud secrets versions add jmgl-client-key-hashes --data-file=-
printf '%s' "<admin-hash>"  | gcloud secrets versions add jmgl-admin-key-hashes  --data-file=-
printf '%s' "<random>"      | gcloud secrets versions add jmgl-audit-hash-secret --data-file=-
# dashboard (run from the repo root):
BUCKET=$(terraform -chdir=deploy/terraform/gcp-cloud-run output -raw web_bucket)
(cd web && npm ci && npm run build)
gsutil -h "Cache-Control:no-cache" cp web/dist/index.html web/dist/config.js web/dist/favicon.svg gs://$BUCKET/
gsutil -m -h "Cache-Control:public,max-age=31536000,immutable" rsync -r web/dist/assets gs://$BUCKET/assets
# DNS: A record for your domain -> terraform output load_balancer_ip (managed TLS cert then provisions)
```

What it creates: one Cloud Run service per region (internal-LB ingress only), serverless NEGs,
one global external Application Load Balancer with managed TLS and HTTP→HTTPS redirect, Cloud
Armor per-IP rate limiting, a Cloud Storage bucket + Cloud CDN for the dashboard, Secret Manager
secrets, a Cloud SQL PostgreSQL instance for the audit log, and a least-privilege service account.
Configure a remote state backend (GCS bucket) before real use; state contains the generated DB
password.

## Kubernetes (Helm)

```bash
kubectl create namespace jmgl
kubectl -n jmgl create secret generic jmgl-api \
  --from-literal=JMGL_CLIENT_KEY_HASHES=<hash> --from-literal=JMGL_ADMIN_KEY_HASHES=<hash> \
  --from-literal=JMGL_AUDIT_DATABASE_URL='postgresql+psycopg://user:pass@host:5432/jmgl' \
  --from-literal=JMGL_AUDIT_HASH_SECRET=<random>
helm install jmgl deploy/helm/jmgl -n jmgl \
  --set api.existingSecret=jmgl-api \
  --set api.image.repository=REGISTRY/jmgl-api --set web.image.repository=REGISTRY/jmgl-web \
  --set ingress.enabled=true --set ingress.host=jmgl.example.org
```

The chart includes: Deployments for API and dashboard (non-root, read-only root FS, dropped
capabilities, seccomp), startup/liveness/readiness probes (`/healthz`, `/readyz`), resource
requests/limits, HPA (CPU 70%, 2–10 API replicas), PodDisruptionBudget, zone spreading,
NetworkPolicy, optional ServiceMonitor, and an Ingress that exposes only `/v1`, `/healthz`,
`/readyz` and the dashboard (not `/metrics` or `/docs`). Use a managed PostgreSQL (Cloud SQL,
RDS, Azure Database) rather than running Postgres in the cluster.

## Operating notes

* **One worker per container**, scale with replicas (metrics are per process). The API uses
  ~270 MB RAM with the model loaded; 512 MB–1 GB limits are comfortable.
* **Readiness:** `/readyz` returns 503 if the audit store is down (when `JMGL_AUDIT_REQUIRED=true`)
  or if the model is missing and `JMGL_REQUIRE_MODEL=true`; otherwise `degraded` with 200.
* **Rate limits** are per process unless `JMGL_RATE_LIMIT_REDIS_URL` is set; add edge limits.
* **Upgrades:** rolling updates with `maxUnavailable: 0`; the audit table is created if missing.
* **Backups:** enable automated backups + point-in-time recovery on the database (on in the
  Terraform example) and test a restore.
