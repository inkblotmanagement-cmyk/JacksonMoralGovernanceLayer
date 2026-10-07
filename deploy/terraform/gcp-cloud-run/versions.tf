terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
  # Configure remote state before real use, e.g.:
  # backend "gcs" { bucket = "YOUR-TF-STATE-BUCKET" prefix = "jmgl" }
}

provider "google" {
  project = var.project_id
}
