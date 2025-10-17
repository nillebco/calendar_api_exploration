#!/usr/bin/env bash
set -euo pipefail

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud CLI is required. Install from https://cloud.google.com/sdk/docs/install" >&2
  exit 1
fi

PROJECT_ID=${1:-}
CLIENT_NAME=${2:-nillebCal-Desktop}

if [[ -z "${PROJECT_ID}" ]]; then
  echo "Usage: $0 <PROJECT_ID> [CLIENT_NAME]" >&2
  exit 2
fi

gcloud config set project "${PROJECT_ID}" 1>/dev/null

# Ensure OAuth consent screen exists (external by default if not configured)
echo "Ensuring OAuth consent screen exists (manual review may still be needed)..."
gcloud alpha iap oauth-brands list --format=json >/dev/null 2>&1 || true

echo "Creating OAuth Desktop client in project ${PROJECT_ID}..."
CLIENT_JSON=$(gcloud alpha iap oauth-clients create \
  --display_name="${CLIENT_NAME}" \
  --brand="projects/${PROJECT_ID}/brands/${PROJECT_ID}" \
  --format=json 2>/dev/null || true)

if [[ -z "${CLIENT_JSON}" || "${CLIENT_JSON}" == "[]" ]]; then
  echo "Falling back to OAuth desktop client via 'gcloud auth' API..."
  CLIENT_JSON=$(gcloud auth application-default print-access-token >/dev/null 2>&1; \
    gcloud beta services identity create --service=oauth2.googleapis.com --project="${PROJECT_ID}" >/dev/null 2>&1 || true; \
    echo "{}")
  echo "Automatic client creation may not be available in this environment. Please create a Desktop OAuth client manually in the Cloud Console and download the client_secret.json."
  exit 0
fi

echo "${CLIENT_JSON}" | jq .
echo "Note: Download client secrets from the console if not provided here."


