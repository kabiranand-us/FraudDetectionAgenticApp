#!/usr/bin/env bash
# Open the private Cloud Run dashboard at http://localhost:8080 (Ctrl+C to stop).
#
# Acts as the fraud-dashboard-invoker service account, because gcloud cannot mint
# Cloud Run tokens for personal logins. Your account needs access first:
#   deploy/cloud_run.sh --grant user:you@example.com
# Tokens last an hour, so the proxy restarts with a fresh one every 55 minutes.
set -euo pipefail

PROJECT="${GCP_PROJECT_ID:-project-8e0caa5b-233c-4e40-823}"
REGION="${REGION:-asia-south1}"
PORT="${PORT:-8080}"
INVOKER_SA="fraud-dashboard-invoker@${PROJECT}.iam.gserviceaccount.com"

URL=$(gcloud run services describe fraud-dashboard --project="$PROJECT" --region="$REGION" \
  --impersonate-service-account="$INVOKER_SA" --format="value(status.url)" 2>/dev/null)
PROXY="$(dirname "$(command -v gcloud)")/cloud-run-proxy"
[[ -x "$PROXY" ]] || { echo "Missing cloud-run-proxy: run 'gcloud components install cloud-run-proxy'"; exit 1; }

echo "Dashboard: http://localhost:$PORT  (proxying to $URL)"
while true; do
  TOKEN=$(gcloud auth print-identity-token --impersonate-service-account="$INVOKER_SA" \
    --audiences="$URL" --include-email 2>/dev/null)
  "$PROXY" -host "$URL" -token "$TOKEN" -bind "127.0.0.1:$PORT" -server-up-time 55m || true
done
