# Deployment configs

| Path | What |
|---|---|
| `helm/jmgl/` | Helm chart for Kubernetes (API + dashboard, HPA, PDB, probes, NetworkPolicy) |
| `terraform/gcp-cloud-run/` | Terraform example: Cloud Run in several regions behind a global HTTPS LB with Cloud Armor and Cloud CDN |
| `../docker-compose.yml` | Local full stack (API + dashboard + PostgreSQL) |
| `../render.yaml` | Render Blueprint |
| `../fly.toml` | Fly.io app config for the API |

See [../docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md). None of these run automatically.
