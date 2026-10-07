output "load_balancer_ip" {
  description = "Point an A record for var.domain at this address."
  value       = google_compute_global_address.ip.address
}

output "web_bucket" {
  description = "Upload the dashboard build here: gsutil -m rsync -r -d web/dist gs://BUCKET"
  value       = google_storage_bucket.web.name
}

output "artifact_registry" {
  value = "${var.primary_region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "cloud_run_services" {
  value = { for r, s in google_cloud_run_v2_service.api : r => s.name }
}

output "secrets_to_populate" {
  description = "Add values with: printf '%s' VALUE | gcloud secrets versions add NAME --data-file=-"
  value       = [for k, s in google_secret_manager_secret.s : s.secret_id if k != "audit_db_url" || !var.create_database]
}
