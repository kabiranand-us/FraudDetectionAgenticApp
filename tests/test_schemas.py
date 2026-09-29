import csv

import pytest

from fraud_agent.config import RAW_DATA_DIR
from fraud_agent.ingest.load_bigquery import SQL_DIR
from fraud_agent.ingest.schemas import RAW_TABLES


@pytest.mark.parametrize("table", RAW_TABLES, ids=lambda t: t.name)
def test_schema_matches_csv_header(table):
    with (RAW_DATA_DIR / table.csv_file).open() as f:
        header = next(csv.reader(f))
    assert [col for col, _ in table.columns] == header


@pytest.mark.parametrize("table", RAW_TABLES, ids=lambda t: t.name)
def test_clean_sql_exists(table):
    sql = (SQL_DIR / f"{table.name}.sql").read_text()
    assert f"fraud_clean.{table.name}" in sql
    assert f"fraud_raw.{table.name}" in sql
