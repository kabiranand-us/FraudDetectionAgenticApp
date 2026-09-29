"""Project configuration, read from environment / .env."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = ROOT / "data" / "raw"

DATASET_RAW = "fraud_raw"
DATASET_CLEAN = "fraud_clean"
DATASET_FEATURES = "fraud_features"
DATASET_CASES = "fraud_cases"
ALL_DATASETS = (DATASET_RAW, DATASET_CLEAN, DATASET_FEATURES, DATASET_CASES)


@dataclass(frozen=True)
class Settings:
    project_id: str | None
    location: str
    agent_model: str


def get_settings() -> Settings:
    load_dotenv(ROOT / ".env")
    return Settings(
        project_id=os.getenv("GCP_PROJECT_ID") or None,
        location=os.getenv("BQ_LOCATION", "asia-south1"),
        agent_model=os.getenv("AGENT_MODEL", "gemini-3.7-flash"),
    )
