"""Load the source CSVs into BigQuery and build the cleaned tables.

    uv run fraud-load                      # uses GCP_PROJECT_ID / BQ_LOCATION from .env
    uv run fraud-load --project my-proj --location asia-south1
    uv run fraud-load --skip-clean         # raw load only

Steps:
  1. Create datasets fraud_raw, fraud_clean, fraud_features, fraud_cases (if missing).
  2. Load each CSV into fraud_raw.<table>, replacing existing data.
  3. Run ingest/sql/<table>.sql to build fraud_clean.<table>.
  4. Check row counts: CSV == raw == clean.
"""

import argparse
import sys
from pathlib import Path

from google.cloud import bigquery
from google.cloud.exceptions import Conflict

from fraud_agent.config import (
    ALL_DATASETS,
    DATASET_CLEAN,
    DATASET_RAW,
    RAW_DATA_DIR,
    get_settings,
)
from fraud_agent.ingest.schemas import RAW_TABLES, RawTable

SQL_DIR = Path(__file__).parent / "sql"


def ensure_datasets(client: bigquery.Client, location: str) -> None:
    for name in ALL_DATASETS:
        dataset = bigquery.Dataset(f"{client.project}.{name}")
        dataset.location = location
        try:
            client.create_dataset(dataset)
            print(f"  created dataset {name}")
        except Conflict:
            existing = client.get_dataset(dataset.reference)
            if existing.location.lower() != location.lower():
                sys.exit(
                    f"Dataset {name} exists in {existing.location}, not {location}. "
                    "Use --location to match it."
                )
            print(f"  dataset {name} exists")


def csv_row_count(path: Path) -> int:
    with path.open(encoding="utf-8") as f:
        return sum(1 for _ in f) - 1  # minus header


def load_raw(client: bigquery.Client, table: RawTable, data_dir: Path) -> int:
    path = data_dir / table.csv_file
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        schema=table.schema,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        max_bad_records=0,
    )
    with path.open("rb") as f:
        job = client.load_table_from_file(
            f, f"{client.project}.{DATASET_RAW}.{table.name}", job_config=job_config
        )
    job.result()
    return job.output_rows


def build_clean(client: bigquery.Client, table: RawTable) -> None:
    sql = (SQL_DIR / f"{table.name}.sql").read_text()
    client.query(sql).result()


def table_row_count(client: bigquery.Client, dataset: str, name: str) -> int:
    return client.get_table(f"{client.project}.{dataset}.{name}").num_rows


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", default=settings.project_id,
                        help="GCP project (default: GCP_PROJECT_ID or gcloud default)")
    parser.add_argument("--location", default=settings.location)
    parser.add_argument("--data-dir", type=Path, default=RAW_DATA_DIR)
    parser.add_argument("--skip-clean", action="store_true")
    args = parser.parse_args()

    client = bigquery.Client(project=args.project, location=args.location)
    print(f"Project {client.project}, location {args.location}")

    print("Datasets:")
    ensure_datasets(client, args.location)

    print("Loading raw tables:")
    failures = []
    for table in RAW_TABLES:
        expected = csv_row_count(args.data_dir / table.csv_file)
        loaded = load_raw(client, table, args.data_dir)
        status = "ok" if loaded == expected else "MISMATCH"
        print(f"  {DATASET_RAW}.{table.name}: {loaded} rows (csv {expected}) {status}")
        if loaded != expected:
            failures.append(f"raw {table.name}")

    if not args.skip_clean:
        print("Building clean tables:")
        for table in RAW_TABLES:
            build_clean(client, table)
            raw = table_row_count(client, DATASET_RAW, table.name)
            clean = table_row_count(client, DATASET_CLEAN, table.name)
            status = "ok" if raw == clean else "MISMATCH"
            print(f"  {DATASET_CLEAN}.{table.name}: {clean} rows {status}")
            if raw != clean:
                failures.append(f"clean {table.name}")

    if failures:
        sys.exit(f"Row count mismatches: {', '.join(failures)}")
    print("Done.")


if __name__ == "__main__":
    main()
