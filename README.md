# Fraud Detection AI Agent

A production-ready, hybrid insurance fraud detection and autonomous investigation platform built on **Google Cloud BigQuery**, **Scikit-Learn**, and **Google Agent Development Kit (ADK)** powered by Gemini on Vertex AI.

---

## 📌 Overview

Traditional fraud systems suffer from either high false-positive rates (rigid rules) or black-box unexplainability (pure ML). This repository implements a **three-tier defense-in-depth architecture**:

1. **Deterministic Rules Engine (BigQuery)**: Rapidly flags known fraud patterns, policy anomalies, bounced payments, and ghost-broking rings using severity-weighted SQL rules calibrated on empirical precision.
2. **Machine Learning Model (HistGradientBoosting)**: Uncovers multi-dimensional non-linear risk factors across policies, claims, agent historical performance, and customer claim frequencies using cross-validated gradient-boosted decision trees.
3. **Autonomous Investigation Agent (Google ADK & Gemini)**: Investigates flagged claims like an expert Special Investigation Unit (SIU) investigator. It queries BigQuery using dedicated read-only investigation tools, compares evidence against historical baselines, cites exact record IDs, and produces structured risk assessments and recommended actions.

```
                     ┌──────────────────────────────────┐
                     │   Raw Insurance Data (4 CSVs)    │
                     │ Policies, Claims, Payments, GB   │
                     └─────────────────┬────────────────┘
                                       │  fraud-load
                                       ▼
                     ┌──────────────────────────────────┐
                     │       BigQuery Clean Layer       │
                     │  Typed dates, normalized values  │
                     │       dq_* validation flags      │
                     └─────────┬──────────────┬─────────┘
                               │              │
             ┌─────────────────┘              └──────────────────┐
             ▼                                                   ▼
┌───────────────────────────────┐               ┌─────────────────────────────────┐
│     BigQuery Rules Engine     │               │    Feature Engineering & ML     │
│   fraud_features.rule_hits    │──────────────▶│       HistGradientBoosting      │
│   fraud_features.rule_scores  │               │ fraud_features.claim_model_scores│
└──────────────┬────────────────┘               └────────────────┬────────────────┘
               │                                                 │
               └───────────────────────┬─────────────────────────┘
                                       ▼
                     ┌──────────────────────────────────┐
                     │   Google ADK Investigation Agent │
                     │       (Gemini 3.8 Flash)         │
                     │   Autonomous tool-calling loop:  │
                     │   • get_claim    • get_policy    │
                     │   • get_customer • get_agent     │
                     │   • find_related_claims          │
                     └─────────────────┬────────────────┘
                                       ▼
                     ┌──────────────────────────────────┐
                     │  Structured SIU ClaimFindings    │
                     │ • Risk level & suspected types   │
                     │ • Cited evidence & mitigations   │
                     │ • Action: SIU / Hold / Approve   │
                     │ • fraud_cases.claim_findings     │
                     └──────────────────────────────────┘
```

---

## 🏛️ System Architecture

### 1. Data Pipeline & BigQuery Datasets

The platform partitions data across 4 BigQuery datasets:

| Dataset | Purpose & Contents |
|---|---|
| **`fraud_raw`** | Direct ingestion of source CSVs (`claims`, `policies`, `payments`, `ghost_broking`) with raw string dates. |
| **`fraud_clean`** | Standardized tables with parsed `DATE` columns, `NULLIF` mappings, and data-quality indicators (`dq_*`). |
| **`fraud_features`** | Feature store housing `rule_hits`, `rule_scores`, engineered tabular ML features (`claim_features`), and model probability scores (`claim_model_scores`). |
| **`fraud_cases`** | Operational case repository storing structured agent findings (`claim_findings`), audit logs, and decisions. |

### 2. Strict Label Leakage Prevention (Honest Evaluation)
To ensure machine learning models and AI agents do not cheat during training and evaluation:
* **Hidden Ground Truth**: Columns `fraud_flag`, `fraud_type`, `claim_status`, and `approved_amount` are strictly forbidden.
* **Rules Guardrail**: `load_rules()` rejects any rule containing forbidden columns.
* **Tools Redaction**: BigQuery agent tools (`bigquery_tools.py`) actively filter out these columns from query results before Gemini sees them.
* **Leakage-Free Features**: `claim_features.sql` excludes post-investigation outcomes and cancellation statuses that could leak fraud labels.

---

## 🔍 The Three Detection Tiers

### Tier 1: BigQuery Rules Engine (`fraud-rules`)
* Defined declaratively in [`fraud_agent/rules/rules.yaml`](file:///Users/neoxdev/Documents/FraudDetectionAiAgent/fraud_agent/rules/rules.yaml).
* Covers 4 insurance fraud domains:
  * **Policies**: Premium never collected, backdated policy issuance, free-look cancellations.
  * **Claims**: Altered documentation, claim exceeding sum insured, early claims (<30 days).
  * **Payments**: Duplicate receipt numbers, unremitted premiums, delayed remittances (>7 days), bounced/reversed transactions.
  * **Ghost Broking**: Unlicensed agents, expired credentials, customer unawareness, repeat complaints.
* Calibrated severities based on empirical precision:
  * **Critical** ($\ge 95\%$ precision, weight `1.0`)
  * **High** ($\ge 60\%$ precision, weight `0.7`)
  * **Medium** ($\ge 25\%$ precision, weight `0.4`)

### Tier 2: Claims ML Model (`fraud-train-claims`)
* **Algorithm**: Scikit-Learn's `HistGradientBoostingClassifier` with native categorical feature support.
* **Cross-Validation**: 5-Fold `StratifiedGroupKFold` grouped by `agent_id`. This guarantees that claims for any sales agent are evaluated strictly on models that never saw that agent's claims during training.
* **Metrics**: Evaluates Area Under the Precision-Recall Curve (PR-AUC) and ROC-AUC against baseline rules.
* **Threshold Tuning**: Automatically solves for precision operating points (90%, 80%, 60%) to maximize recall for investigator workloads.
* **Artifact**: Serialized to `fraud_agent/models/artifacts/claims_model.joblib`.

### Tier 3: Autonomous Investigation Agent (`fraud-investigate` & ADK Web)
* **Engine**: Google Agent Development Kit (`google-adk`) utilizing Gemini (default: `gemini-3.8-flash`).
* **Tool Suite**:
  * `get_claim(claim_id)`: Claim attributes, rule triggers, ML score, policy limits.
  * `find_related_claims(claim_id, window_days)`: Temporal duplicate detector across same customer, same policy, or same agent.
  * `get_agent_profile(agent_id)`: Licensing veracity, complaint history, peer baseline comparisons.
  * `get_customer_history(customer_id)`: Multi-policy claim frequency and payment behavior.
  * `get_policy(policy_id)`: Contract terms and premium payment reconciliation.
* **Output Schema**: Pydantic-enforced `ClaimFindings`:
  * `risk_level`: `critical`, `high`, `medium`, `low`
  * `suspected_fraud_types`: Duplicate claims, staged accident, fake documents, exaggerated claims, early claims.
  * `evidence`: List of specific facts directly citing source table and record ID.
  * `mitigating_factors`: Facts supporting legitimacy (e.g. clean payment history, prompt reporting).
  * `recommended_action`: `reject_and_refer_to_siu`, `hold_for_investigation`, `request_documents`, `approve`.
  * `summary`: 20-second executive summary for human adjusters.

---

## 📂 Project Layout

```
FraudDetectionAiAgent/
├── data/
│   └── raw/                           # Source CSV datasets
│       ├── claims.csv                 # Claim records & fraud labels
│       ├── ghost_broking.csv          # Agent licensing & unauthorized brokers
│       ├── payments_bad_payments.csv  # Premium remittances, bounces & receipts
│       └── policies_free_insurance.csv# Policy issues, cancellations & terms
├── fraud_agent/
│   ├── config.py                      # Environment & BigQuery settings
│   ├── agents/
│   │   ├── claims_agent/
│   │   │   └── agent.py               # ADK LlmAgent setup & prompt guidelines
│   │   ├── run_claims.py              # CLI batch runner, evaluation & BigQuery persistence
│   │   └── schemas.py                 # Pydantic schemas (ClaimFindings, Evidence)
│   ├── ingest/
│   │   ├── load_bigquery.py           # Ingestion script (raw -> clean)
│   │   ├── schemas.py                 # BigQuery table schema definitions
│   │   └── sql/                       # BigQuery transformation SQL scripts
│   ├── models/
│   │   ├── claims_model.py            # Gradient boosting training & CV pipeline
│   │   ├── artifacts/                 # Saved model joblib artifacts
│   │   └── sql/claim_features.sql     # Leakage-free feature extraction SQL
│   ├── rules/
│   │   ├── engine.py                  # BigQuery rules compiler & evaluation engine
│   │   └── rules.yaml                 # Declarative business rules & severities
│   ├── tools/
│   │   └── bigquery_tools.py          # BigQuery agent tools (redacted labels)
│   └── graph/                         # Entity resolution & graph features (extensible)
├── tests/
│   ├── test_claims_agent.py           # Verification of tool redaction & ADK agent wiring
│   ├── test_claims_model.py           # Test against feature label leaks & threshold math
│   ├── test_rules.py                  # YAML rule syntax & label exclusion validation
│   └── test_schemas.py                # Schema-to-CSV alignment tests
├── pyproject.toml                     # Python dependencies & console scripts
└── .env.example                       # Environment variable templates
```

---

## 🚀 Quickstart & Usage

### 1. Prerequisites & Environment Setup

This project uses [`uv`](https://github.com/astral-sh/uv) for fast Python package management.

```bash
# 1. Install dependencies into a virtual environment
uv sync

# 2. Configure environment variables
cp .env.example .env
```

Edit your `.env` file:
```dotenv
GCP_PROJECT_ID=your-gcp-project-id
BQ_LOCATION=asia-south1
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=global
AGENT_MODEL=gemini-3.8-flash
```

Authenticate with Google Cloud Application Default Credentials (ADC):
```bash
gcloud auth application-default login
```

### 2. Verify Installation

Run the complete test suite:
```bash
uv run pytest
```

### 3. Step-by-Step Execution Workflow

#### Step A: Ingest Data into BigQuery
Loads raw CSVs into `fraud_raw`, applies cleaning SQL, and builds `fraud_clean`:
```bash
uv run fraud-load
```
*Flags: `--project <PROJECT_ID>`, `--location <LOCATION>`, `--skip-clean`*

#### Step B: Execute the Rules Engine
Evaluates all rules in BigQuery and populates `fraud_features.rule_hits` and `fraud_features.rule_scores`:
```bash
# Optional dry run to check SQL validity without writing
uv run fraud-rules --dry-run

# Run and evaluate
uv run fraud-rules
```

#### Step C: Train the Machine Learning Model
Generates `claim_features`, runs grouped cross-validation, reports PR-AUC / ROC-AUC, populates `fraud_features.claim_model_scores`, and saves model artifact:
```bash
uv run fraud-train-claims
```

#### Step D: Run Autonomous Claims Investigations
Investigate specific claim IDs or run a benchmark sample evaluated against ground truth:

```bash
# Investigate specific claim IDs
uv run fraud-investigate CLM000004 CLM000017

# Run stratified evaluation on 20 claims from the tuning split
uv run fraud-investigate --sample 20 --split tune

# Run evaluation on the test split and persist findings to fraud_cases.claim_findings
uv run fraud-investigate --sample 20 --split test --save
```

#### Step E: Interactive Agent Web UI
Explore and chat with the Claims Agent directly in Google ADK's built-in web interface:
```bash
uv run adk web fraud_agent/agents
```
Open your browser at `http://localhost:8000` to interactively inspect claims, verify cited evidence, and ask follow-up questions.

---

## 📊 Summary of Commands

| Command | Entrypoint | Description |
|---|---|---|
| `uv run fraud-load` | `fraud_agent.ingest.load_bigquery:main` | Ingests CSVs and builds clean BigQuery tables |
| `uv run fraud-rules` | `fraud_agent.rules.engine:main` | Evaluates declarative SQL rules in BigQuery |
| `uv run fraud-train-claims` | `fraud_agent.models.claims_model:main` | Trains gradient-boosted trees and scores claims |
| `uv run fraud-investigate` | `fraud_agent.agents.run_claims:main` | Runs Gemini ADK agent on claims (CLI / batch eval) |
| `uv run adk web fraud_agent/agents` | `google.adk` CLI | Launches the local interactive web UI |
| `uv run pytest` | `pytest` | Runs unit and integration tests |

---

## 🔒 Security & Data Governance

* **Zero Direct SQL Injection**: All investigative agent tools utilize Google Cloud BigQuery scalar and array parameterized queries.
* **Cost Controls**: Every query executed by agent tools enforces `maximum_bytes_billed = 100 MB` and row caps (`max_results = 50`).
* **Audit Trail**: Every finding generated by the agent is structured, timestamped, tracks model versions, and can be saved to `fraud_cases.claim_findings` for regulatory compliance.

The alert pipeline (`fraud_agent/agents/fraud_investigation`) is an ADK
`SequentialAgent`: the orchestrator takes one alert, calls the matching specialist
(claims, policy, payment or ghost-broking agent, each an `AgentTool`), adds
context, and writes notes; the case writer turns the notes into a validated
`CaseFile` using only facts in the notes; the reviewer, which never sees the notes,
re-checks every cited ID and fact against BigQuery and corrects risk, action and
fraud types. Each specialist can only name its own file's fraud types. Alerts come from rules (high or critical) and the claims model
(score >= 0.42); the agents' risk assessment is advice, not the flag.

## Investigator console

React (Vite, TypeScript) in `frontend/`, served by the FastAPI app in
`fraud_agent/api/`. One command runs both once the frontend is built:

```bash
cd frontend && npm install && npm run build && cd ..
uv run fraud-api
```

Then open http://localhost:8000. For frontend work, run `npm run dev` in
`frontend/` (port 5173, proxies /api to port 8000) alongside `uv run fraud-api`.

The console shows the alert queue with status (open, case ready, decided); each
case with the reviewer's check of every fact, the people involved and network
context; an "Investigate now" button that runs the agent pipeline as a background
job the page polls; a decision form writing to `fraud_cases.decisions`; the
networks view; and the decisions log. It never shows label columns.

API endpoints are documented at http://localhost:8000/api/docs.

## Deploying

`deploy/cloud_run.sh` deploys the console (React build + FastAPI) to Cloud Run (asia-south1), privately:
it enables the Cloud Run, Cloud Build and Artifact Registry APIs, creates a
`fraud-dashboard` service account with least privilege (BigQuery job user, Vertex
AI user, read `fraud_clean` and `fraud_features`, write `fraud_cases`), and
deploys with `--no-allow-unauthenticated`. `deploy/cloud_run.sh --update`
redeploys code only.

Open the private service from your machine:

```bash
deploy/open_dashboard.sh
```

then browse http://localhost:8080. It acts as the `fraud-dashboard-invoker`
service account (gcloud cannot mint Cloud Run tokens for personal logins) and
renews its token every 55 minutes. Give a colleague access with
`deploy/cloud_run.sh --grant user:EMAIL`.
