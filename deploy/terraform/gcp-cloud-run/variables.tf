variable "project_id" {
  description = "Google Cloud project id (must already exist with billing enabled)."
  type        = string
}

variable "name" {
  description = "Prefix for all resource names."
  type        = string
  default     = "jmgl"
}

variable "regions" {
  description = "Cloud Run regions. The global load balancer sends each user to the nearest healthy region."
  type        = list(string)
  default     = ["us-east1", "europe-west1"]
}

variable "primary_region" {
  description = "Region for the audit database and the Artifact Registry repository."
  type        = string
  default     = "us-east1"
}

variable "api_image" {
  description = "Full image reference for the API, e.g. us-east1-docker.pkg.dev/PROJECT/jmgl/jmgl-api:0.5.0"
  type        = string
}

variable "domain" {
  description = "Public hostname (DNS A record must point at the load balancer IP output)."
  type        = string
}

variable "cors_origins" {
  description = "Comma-separated browser origins allowed to call the API directly."
  type        = string
  default     = ""
}

variable "min_instances" {
  description = "Minimum Cloud Run instances per region (0 = scale to zero; first request pays a ~5-10 s cold start)."
  type        = number
  default     = 0
}

variable "max_instances" {
  description = "Maximum Cloud Run instances per region."
  type        = number
  default     = 10
}

variable "create_database" {
  description = "Create a Cloud SQL PostgreSQL instance for the audit log. If false, set audit_database_url_secret yourself."
  type        = bool
  default     = true
}

variable "db_tier" {
  description = "Cloud SQL machine tier."
  type        = string
  default     = "db-f1-micro"
}

variable "audit_retention_days" {
  type    = number
  default = 90
}

variable "rate_limit_per_minute" {
  description = "Edge rate limit per client IP (Cloud Armor), in addition to the per-key limit in the API."
  type        = number
  default     = 300
}

variable "deletion_protection" {
  type    = bool
  default = true
}
