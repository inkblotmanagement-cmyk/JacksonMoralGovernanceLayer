# JMGL on Google Cloud Run in several regions behind one global HTTPS load balancer.
#
#   users ──► global external Application LB (managed TLS, Cloud Armor rate limit)
#               ├─ /v1/*, /healthz, /readyz ─► serverless NEG per region ─► Cloud Run "jmgl-api-<region>"
#               └─ everything else ─────────► Cloud Storage bucket + Cloud CDN (dashboard static files)
#
# Example only: review costs (see docs/DEPLOYMENT.md) and data-residency notes
# (docs/MULTI_REGION.md, docs/DATA_PROTECTION.md) before applying. Nothing here runs automatically.

locals {
  services = toset([
    "run.googleapis.com", "compute.googleapis.com", "secretmanager.googleapis.com",
    "sqladmin.googleapis.com", "artifactregistry.googleapis.com",
  ])
}

resource "google_project_service" "apis" {
  for_each           = local.services
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "images" {
  location      = var.primary_region
  repository_id = var.name
  format        = "DOCKER"
  description   = "JMGL container images"
  depends_on    = [google_project_service.apis]
}

# ---------------------------------------------------------------- identity & secrets
resource "google_service_account" "api" {
  account_id   = "${var.name}-api"
  display_name = "JMGL API (Cloud Run)"
}

# Secret *containers* are created here; add the values yourself so they never sit in TF state:
#   printf '%s' "<sha256-hash>,<sha256-hash>" | gcloud secrets versions add jmgl-client-key-hashes --data-file=-
locals {
  secret_ids = {
    client_key_hashes = "${var.name}-client-key-hashes"
    admin_key_hashes  = "${var.name}-admin-key-hashes"
    audit_hash_secret = "${var.name}-audit-hash-secret"
    audit_db_url      = "${var.name}-audit-database-url"
  }
}

resource "google_secret_manager_secret" "s" {
  for_each  = local.secret_ids
  secret_id = each.value
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_iam_member" "api_access" {
  for_each  = google_secret_manager_secret.s
  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

# ---------------------------------------------------------------- audit database
resource "random_password" "db" {
  count   = var.create_database ? 1 : 0
  length  = 32
  special = false
}

resource "google_sql_database_instance" "audit" {
  count               = var.create_database ? 1 : 0
  name                = "${var.name}-audit"
  region              = var.primary_region
  database_version    = "POSTGRES_16"
  deletion_protection = var.deletion_protection
  settings {
    tier              = var.db_tier
    availability_type = "ZONAL" # use REGIONAL for HA (roughly doubles cost)
    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }
    # Public IP is reached only through the Cloud SQL connector (IAM-authorised, TLS); no authorised
    # networks are configured. For private IP, add a VPC + Direct VPC egress (docs/MULTI_REGION.md).
    #trivy:ignore:AVD-GCP-0017
    ip_configuration {
      ipv4_enabled = true # reached only through the Cloud SQL connector (IAM-authorised), no authorised networks
      ssl_mode     = "ENCRYPTED_ONLY"
    }
    database_flags {
      name  = "log_min_duration_statement"
      value = "1000"
    }
  }
  depends_on = [google_project_service.apis]
}

resource "google_sql_database" "audit" {
  count    = var.create_database ? 1 : 0
  name     = "jmgl"
  instance = google_sql_database_instance.audit[0].name
}

resource "google_sql_user" "audit" {
  count    = var.create_database ? 1 : 0
  name     = "jmgl"
  instance = google_sql_database_instance.audit[0].name
  password = random_password.db[0].result
}

resource "google_project_iam_member" "api_sql_client" {
  count   = var.create_database ? 1 : 0
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# The DB URL (contains the generated password) is written as a secret version. It is
# therefore present in Terraform state: keep state in a private, encrypted bucket.
resource "google_secret_manager_secret_version" "db_url" {
  count       = var.create_database ? 1 : 0
  secret      = google_secret_manager_secret.s["audit_db_url"].id
  secret_data = "postgresql+psycopg://jmgl:${random_password.db[0].result}@/jmgl?host=/cloudsql/${google_sql_database_instance.audit[0].connection_name}"
}

# ---------------------------------------------------------------- Cloud Run (one service per region)
resource "google_cloud_run_v2_service" "api" {
  for_each            = toset(var.regions)
  name                = "${var.name}-api-${each.value}"
  location            = each.value
  ingress             = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER" # only reachable via the global LB
  deletion_protection = false

  template {
    service_account                  = google_service_account.api.email
    max_instance_request_concurrency = 40
    timeout                          = "30s"
    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }
    containers {
      image = var.api_image
      ports {
        container_port = 8000
      }
      resources {
        limits            = { cpu = "1", memory = "1Gi" }
        cpu_idle          = true
        startup_cpu_boost = true
      }
      env {
        name  = "JMGL_ENVIRONMENT"
        value = "production"
      }
      env {
        name  = "JMGL_REGION"
        value = each.value
      }
      env {
        name  = "JMGL_AUDIT_BACKEND"
        value = "sql"
      }
      env {
        name  = "JMGL_AUDIT_RETENTION_DAYS"
        value = tostring(var.audit_retention_days)
      }
      env {
        name  = "JMGL_CORS_ORIGINS"
        value = var.cors_origins
      }
      env {
        name  = "JMGL_TRUST_PROXY_HEADERS"
        value = "true"
      }
      env {
        name  = "JMGL_METRICS_PUBLIC"
        value = "false"
      }
      env {
        name  = "FORWARDED_ALLOW_IPS"
        value = "*"
      }
      dynamic "env" {
        for_each = {
          JMGL_CLIENT_KEY_HASHES  = "client_key_hashes"
          JMGL_ADMIN_KEY_HASHES   = "admin_key_hashes"
          JMGL_AUDIT_HASH_SECRET  = "audit_hash_secret"
          JMGL_AUDIT_DATABASE_URL = "audit_db_url"
        }
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.s[env.value].secret_id
              version = "latest"
            }
          }
        }
      }
      startup_probe {
        http_get {
          path = "/healthz"
        }
        period_seconds    = 5
        failure_threshold = 24
      }
      liveness_probe {
        http_get {
          path = "/healthz"
        }
        period_seconds = 30
      }
      dynamic "volume_mounts" {
        for_each = var.create_database ? [1] : []
        content {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }
    }
    dynamic "volumes" {
      for_each = var.create_database ? [1] : []
      content {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.audit[0].connection_name]
        }
      }
    }
  }
  depends_on = [google_secret_manager_secret_iam_member.api_access]
}

# The LB (not end users) invokes Cloud Run; API-key auth happens inside JMGL.
resource "google_cloud_run_v2_service_iam_member" "public" {
  for_each = google_cloud_run_v2_service.api
  location = each.value.location
  name     = each.value.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_compute_region_network_endpoint_group" "api" {
  for_each              = google_cloud_run_v2_service.api
  name                  = "${var.name}-neg-${each.key}"
  region                = each.key
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = each.value.name
  }
}

# ---------------------------------------------------------------- edge security
resource "google_compute_security_policy" "edge" {
  name = "${var.name}-edge"
  rule {
    action   = "throttle"
    priority = 1000
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = var.rate_limit_per_minute
        interval_sec = 60
      }
    }
    description = "Per-IP rate limit at the edge"
  }
  rule {
    action   = "allow"
    priority = 2147483647
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "default allow"
  }
}

resource "google_compute_backend_service" "api" {
  name                  = "${var.name}-api"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTPS"
  security_policy       = google_compute_security_policy.edge.id
  dynamic "backend" {
    for_each = google_compute_region_network_endpoint_group.api
    content {
      group = backend.value.id
    }
  }
  log_config {
    enable      = true
    sample_rate = 0.1
  }
}

# ---------------------------------------------------------------- dashboard (static) + CDN
resource "google_storage_bucket" "web" {
  name                        = "${var.project_id}-${var.name}-web"
  location                    = "US" # multi-region bucket; CDN caches at Google edge locations worldwide
  uniform_bucket_level_access = true
  force_destroy               = false
  website {
    main_page_suffix = "index.html"
    not_found_page   = "index.html"
  }
}

# trivy:ignore:AVD-GCP-0001 Intentionally public: the bucket only holds the static dashboard build.
resource "google_storage_bucket_iam_member" "web_public" {
  bucket = google_storage_bucket.web.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

resource "google_compute_backend_bucket" "web" {
  name        = "${var.name}-web"
  bucket_name = google_storage_bucket.web.name
  enable_cdn  = true
  cdn_policy {
    cache_mode        = "USE_ORIGIN_HEADERS"
    client_ttl        = 3600
    default_ttl       = 3600
    max_ttl           = 86400
    negative_caching  = true
    serve_while_stale = 86400
  }
}

# ---------------------------------------------------------------- global load balancer
resource "google_compute_url_map" "lb" {
  name            = "${var.name}-lb"
  default_service = google_compute_backend_bucket.web.id
  host_rule {
    hosts        = [var.domain]
    path_matcher = "main"
  }
  path_matcher {
    name            = "main"
    default_service = google_compute_backend_bucket.web.id
    path_rule {
      paths   = ["/v1/*", "/healthz", "/readyz"]
      service = google_compute_backend_service.api.id
    }
  }
}

resource "google_compute_managed_ssl_certificate" "cert" {
  name = "${var.name}-cert"
  managed {
    domains = [var.domain]
  }
}

resource "google_compute_target_https_proxy" "https" {
  name             = "${var.name}-https"
  url_map          = google_compute_url_map.lb.id
  ssl_certificates = [google_compute_managed_ssl_certificate.cert.id]
}

resource "google_compute_global_address" "ip" {
  name = "${var.name}-ip"
}

resource "google_compute_global_forwarding_rule" "https" {
  name                  = "${var.name}-https"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  ip_address            = google_compute_global_address.ip.address
  port_range            = "443"
  target                = google_compute_target_https_proxy.https.id
}

# HTTP -> HTTPS redirect
resource "google_compute_url_map" "redirect" {
  name = "${var.name}-redirect"
  default_url_redirect {
    https_redirect = true
    strip_query    = false
  }
}

resource "google_compute_target_http_proxy" "http" {
  name    = "${var.name}-http"
  url_map = google_compute_url_map.redirect.id
}

resource "google_compute_global_forwarding_rule" "http" {
  name                  = "${var.name}-http"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  ip_address            = google_compute_global_address.ip.address
  port_range            = "80"
  target                = google_compute_target_http_proxy.http.id
}
