terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_project_service" "calendar_api" {
  project = var.project_id
  service = "calendar-json.googleapis.com"
}

output "project_id" {
  value       = var.project_id
  description = "GCP project id"
}

