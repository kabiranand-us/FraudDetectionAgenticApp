#!/usr/bin/env bash
# Deploy the investigator dashboard to Cloud Run, privately.
#
#   deploy/cloud_run.sh            first deploy: APIs, service account, permissions, deploy
#   deploy/cloud_run.sh --update   redeploy code only
#
# The service does NOT allow unauthenticated access. People open it by acting as
# the fraud-dashboard-invoker service account (gcloud cannot mint Cloud Run
# tokens for personal logins):
#   deploy/cloud_run.sh --grant user:someone@example.com
#   gcloud run services proxy fraud-dashboard --region=asia-south1 --project=$PROJECT \
#     --impersonate-service-account=fraud-dashboard-invoker@$PROJECT.iam.gserviceaccount.com
# then browse http://localhost:8080.
set -euo pipefail

PROJECT="${GCP_PROJECT_ID:-project-8e0caa5b-233c-4e40-823}"
REGION="${REGION:-asia-south1}"
SERVICE="fraud-dashboard"
SA_NAME="fraud-dashboard"
SA="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
# Builds run as their own account instead of the shared default compute account.
BUILD_SA="${SA_NAME}-build@${PROJECT}.iam.gserviceaccount.com"
# Invokes the private service; people act as it to open the dashboard.
INVOKER_SA="${SA_NAME}-invoker@${PROJECT}.iam.gserviceaccount.com"

grant_access() {  # let a person open the dashboard by acting as the invoker account
  gcloud iam service-accounts add-iam-policy-binding "$INVOKER_SA" --project="$PROJECT" \
    --member="$1" --role=roles/iam.serviceAccountTokenCreator --condition=None --quiet >/dev/null
  echo "  $1 can now open the dashboard"
}

if [[ "${1:-}" == "--grant" ]]; then
  grant_access "${2:?usage: deploy/cloud_run.sh --grant user:EMAIL}"
  exit 0
fi
BQ_LOCATION="asia-south1"
AGENT_MODEL="${AGENT_MODEL:-gemini-3.7-flash}"

if [[ "${1:-}" != "--update" ]]; then
  echo "== Enabling APIs"
  gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
    artifactregistry.googleapis.com --project="$PROJECT"

  echo "== Service account $SA"
  gcloud iam service-accounts describe "$SA" --project="$PROJECT" >/dev/null 2>&1 ||
    gcloud iam service-accounts create "$SA_NAME" --project="$PROJECT" \
      --display-name="Fraud investigator dashboard"

  echo "== Build service account $BUILD_SA"
  gcloud iam service-accounts describe "$BUILD_SA" --project="$PROJECT" >/dev/null 2>&1 ||
    gcloud iam service-accounts create "${SA_NAME}-build" --project="$PROJECT" \
      --display-name="Fraud dashboard image builds"

  echo "== Permissions (least privilege)"
  # Run BigQuery queries and call Gemini on Vertex AI.
  # A new service account takes a little while to be usable in IAM policies.
  grant() {  # grant <member> <role>, retrying while a new account propagates
    for attempt in 1 2 3 4 5 6; do
      if gcloud projects add-iam-policy-binding "$PROJECT" --member="$1" \
          --role="$2" --condition=None --quiet >/dev/null 2>&1; then
        echo "  granted $2 to ${1#serviceAccount:}"; return
      fi
      sleep 10
    done
    echo "Could not grant $2 to $1"; exit 1
  }
  # Runtime: run BigQuery queries and call Gemini on Vertex AI.
  grant "serviceAccount:$SA" roles/bigquery.jobUser
  grant "serviceAccount:$SA" roles/aiplatform.user
  # Build: read uploaded source, push the image, write build logs.
  grant "serviceAccount:$BUILD_SA" roles/cloudbuild.builds.builder
  # Read the cleaned data and features; write only case files and decisions.
  bq query --project_id="$PROJECT" --location="$BQ_LOCATION" --use_legacy_sql=false --quiet "
    GRANT \`roles/bigquery.dataViewer\` ON SCHEMA fraud_clean TO 'serviceAccount:$SA';
    GRANT \`roles/bigquery.dataViewer\` ON SCHEMA fraud_features TO 'serviceAccount:$SA';
    GRANT \`roles/bigquery.dataEditor\` ON SCHEMA fraud_cases TO 'serviceAccount:$SA';" >/dev/null
fi

echo "== Building and deploying $SERVICE to $REGION"
gcloud run deploy "$SERVICE" --project="$PROJECT" --region="$REGION" --source=. \
  --service-account="$SA" \
  --build-service-account="projects/$PROJECT/serviceAccounts/$BUILD_SA" \
  --no-allow-unauthenticated \
  --set-env-vars="GCP_PROJECT_ID=$PROJECT,BQ_LOCATION=$BQ_LOCATION,GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=global,AGENT_MODEL=$AGENT_MODEL" \
  --memory=2Gi --cpu=1 --min-instances=0 --max-instances=2 \
  --timeout=3600 --session-affinity --quiet

if [[ "${1:-}" != "--update" ]]; then
  echo "== Invoker service account $INVOKER_SA"
  gcloud iam service-accounts describe "$INVOKER_SA" --project="$PROJECT" >/dev/null 2>&1 ||
    gcloud iam service-accounts create "${SA_NAME}-invoker" --project="$PROJECT" \
      --display-name="Opens the fraud dashboard"
  for attempt in 1 2 3 4 5 6; do
    gcloud run services add-iam-policy-binding "$SERVICE" --project="$PROJECT" --region="$REGION" \
      --member="serviceAccount:$INVOKER_SA" --role=roles/run.invoker --quiet >/dev/null 2>&1 && break
    [[ $attempt == 6 ]] && { echo "Could not grant run.invoker to $INVOKER_SA"; exit 1; }
    sleep 10
  done
  echo "  granted roles/run.invoker on $SERVICE to $INVOKER_SA"
  # The proxy reads the service's settings to find its URL.
  gcloud run services add-iam-policy-binding "$SERVICE" --project="$PROJECT" --region="$REGION" \
    --member="serviceAccount:$INVOKER_SA" --role=roles/run.viewer --quiet >/dev/null
  echo "  granted roles/run.viewer on $SERVICE to $INVOKER_SA"
  grant_access "user:$(gcloud config get-value account 2>/dev/null)"
fi

echo
echo "Deployed privately. Open it with:"
echo "  gcloud run services proxy $SERVICE --region=$REGION --project=$PROJECT \\"
echo "    --impersonate-service-account=$INVOKER_SA"
echo "then browse http://localhost:8080"
