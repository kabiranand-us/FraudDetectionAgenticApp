"""Rules engine: evaluates rules.yaml in BigQuery and writes the results.

    uv run fraud-rules              # evaluate rules, write tables, print baseline report
    uv run fraud-rules --dry-run    # validate the generated SQL only; writes nothing

Writes:
  fraud_features.rule_hits    one row per (record, rule) that fired
  fraud_features.rule_scores  one row per record in every table: score, severity, rule ids

rule_score is the weight of the most severe rule hit (0 when nothing fired).
"""

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from google.cloud import bigquery

from fraud_agent.config import DATASET_CLEAN, DATASET_FEATURES, get_settings
from fraud_agent.ingest.schemas import RAW_TABLES

RULES_FILE = Path(__file__).parent / "rules.yaml"
TABLES = {t.name: t for t in RAW_TABLES}

# Labels and investigation outcomes: a rule using these would leak the answer.
FORBIDDEN_COLUMNS = ("fraud_flag", "fraud_type", "claim_status", "approved_amount")


@dataclass(frozen=True)
class Rule:
    id: str
    table: str
    severity: str
    description: str
    targets: tuple[str, ...]
    condition: str


@dataclass(frozen=True)
class RuleSet:
    severity_weights: dict[str, float]
    rules: tuple[Rule, ...]

    def weight(self, rule: Rule) -> float:
        return self.severity_weights[rule.severity]


def load_rules(path: Path = RULES_FILE) -> RuleSet:
    raw = yaml.safe_load(path.read_text())
    weights = {k: float(v) for k, v in raw["severity_weights"].items()}
    rules = tuple(
        Rule(
            id=r["id"],
            table=r["table"],
            severity=r["severity"],
            description=r["description"],
            targets=tuple(r.get("targets", [])),
            condition=r["condition"],
        )
        for r in raw["rules"]
    )

    seen = set()
    for rule in rules:
        if rule.id in seen:
            raise ValueError(f"Duplicate rule id {rule.id}")
        seen.add(rule.id)
        if rule.table not in TABLES:
            raise ValueError(f"{rule.id}: unknown table {rule.table}")
        if rule.severity not in weights:
            raise ValueError(f"{rule.id}: unknown severity {rule.severity}")
        for col in FORBIDDEN_COLUMNS:
            if re.search(rf"\b{col}\b", rule.condition):
                raise ValueError(f"{rule.id}: condition uses label/outcome column {col}")
    return RuleSet(weights, rules)


def rule_hits_sql(ruleset: RuleSet) -> str:
    selects = []
    for rule in ruleset.rules:
        id_col = TABLES[rule.table].id_column
        selects.append(
            f"SELECT '{rule.table}' AS record_table, r.{id_col} AS record_id,\n"
            f"  r.agent_id, r.customer_id, r.policy_id,\n"
            f"  '{rule.id}' AS rule_id, '{rule.severity}' AS severity,\n"
            f"  {ruleset.weight(rule)} AS weight, CURRENT_TIMESTAMP() AS evaluated_at\n"
            f"FROM {DATASET_CLEAN}.{rule.table} r\n"
            f"WHERE ({rule.condition})"
        )
    return (
        f"CREATE OR REPLACE TABLE {DATASET_FEATURES}.rule_hits AS\n"
        + "\nUNION ALL\n".join(selects)
    )


def rule_scores_sql(ruleset: RuleSet) -> str:
    records = "\n  UNION ALL\n".join(
        f"  SELECT '{t.name}' AS record_table, {t.id_column} AS record_id,"
        f" agent_id, customer_id, policy_id FROM {DATASET_CLEAN}.{t.name}"
        for t in RAW_TABLES
    )
    severity_case = " ".join(
        f"WHEN {w} THEN '{s}'" for s, w in ruleset.severity_weights.items()
    )
    return f"""CREATE OR REPLACE TABLE {DATASET_FEATURES}.rule_scores AS
WITH records AS (
{records}
)
SELECT
  rec.record_table, rec.record_id, rec.agent_id, rec.customer_id, rec.policy_id,
  COUNT(h.rule_id) AS n_rules_hit,
  COALESCE(MAX(h.weight), 0) AS rule_score,
  CASE MAX(h.weight) {severity_case} END AS max_severity,
  ARRAY_AGG(h.rule_id IGNORE NULLS ORDER BY h.weight DESC, h.rule_id) AS rule_ids,
  CURRENT_TIMESTAMP() AS evaluated_at
FROM records rec
LEFT JOIN {DATASET_FEATURES}.rule_hits h USING (record_table, record_id)
GROUP BY rec.record_table, rec.record_id, rec.agent_id, rec.customer_id, rec.policy_id"""


def _labels_cte() -> str:
    return "\n  UNION ALL\n".join(
        f"  SELECT '{t.name}' AS record_table, {t.id_column} AS record_id,"
        f" fraud_flag, fraud_type FROM {DATASET_CLEAN}.{t.name}"
        for t in RAW_TABLES
    )


def threshold_report_sql(ruleset: RuleSet) -> str:
    thresholds = ", ".join(
        f"STRUCT('{s}+' AS level, {w} AS min_score)"
        for s, w in sorted(ruleset.severity_weights.items(), key=lambda kv: -kv[1])
    )
    return f"""WITH labels AS (
{_labels_cte()}
)
SELECT s.record_table AS tbl, t.level,
  COUNTIF(s.rule_score >= t.min_score) AS flagged,
  COUNTIF(s.rule_score >= t.min_score AND l.fraud_flag) AS true_pos,
  COUNTIF(l.fraud_flag) AS total_fraud
FROM {DATASET_FEATURES}.rule_scores s
JOIN labels l USING (record_table, record_id)
CROSS JOIN UNNEST([{thresholds}]) t
GROUP BY tbl, t.level, t.min_score
ORDER BY tbl, t.min_score DESC"""


def rule_report_sql() -> str:
    return f"""WITH labels AS (
{_labels_cte()}
)
SELECT h.record_table AS tbl, h.rule_id, h.severity,
  COUNT(*) AS hits, COUNTIF(l.fraud_flag) AS true_pos
FROM {DATASET_FEATURES}.rule_hits h
JOIN labels l USING (record_table, record_id)
GROUP BY tbl, h.rule_id, h.severity
ORDER BY tbl, h.rule_id"""


def fraud_type_report_sql(ruleset: RuleSet) -> str:
    high = ruleset.severity_weights.get("high", 0)
    return f"""WITH labels AS (
{_labels_cte()}
)
SELECT l.record_table AS tbl, l.fraud_type, COUNT(*) AS n,
  COUNTIF(s.rule_score >= {high}) AS caught_high,
  COUNTIF(s.rule_score > 0) AS caught_any
FROM labels l
JOIN {DATASET_FEATURES}.rule_scores s USING (record_table, record_id)
WHERE l.fraud_flag
GROUP BY tbl, l.fraud_type
ORDER BY tbl, n DESC"""


def _pct(num: int, den: int) -> str:
    return f"{100 * num / den:5.1f}%" if den else "    -"


def print_report(client: bigquery.Client, ruleset: RuleSet) -> None:
    print("\nBaseline by severity threshold (precision = fraud share of flagged, recall = share of fraud caught)")
    print(f"  {'table':<14}{'level':<11}{'flagged':>8}{'precision':>11}{'recall':>9}")
    for row in client.query(threshold_report_sql(ruleset)).result():
        print(f"  {row.tbl:<14}{row.level:<11}{row.flagged:>8}"
              f"{_pct(row.true_pos, row.flagged):>11}{_pct(row.true_pos, row.total_fraud):>9}")

    print("\nPer rule")
    print(f"  {'rule':<28}{'severity':<10}{'hits':>6}{'precision':>11}")
    for row in client.query(rule_report_sql()).result():
        print(f"  {row.rule_id:<28}{row.severity:<10}{row.hits:>6}{_pct(row.true_pos, row.hits):>11}")

    print("\nRecall per fraud type")
    print(f"  {'table':<14}{'fraud type':<40}{'n':>5}{'high+':>9}{'any':>9}")
    for row in client.query(fraud_type_report_sql(ruleset)).result():
        print(f"  {row.tbl:<14}{row.fraud_type:<40}{row.n:>5}"
              f"{_pct(row.caught_high, row.n):>9}{_pct(row.caught_any, row.n):>9}")


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", default=settings.project_id)
    parser.add_argument("--location", default=settings.location)
    parser.add_argument("--dry-run", action="store_true",
                        help="validate the rule SQL in BigQuery without writing anything")
    parser.add_argument("--no-report", action="store_true")
    args = parser.parse_args()

    ruleset = load_rules()
    client = bigquery.Client(project=args.project, location=args.location)
    print(f"{len(ruleset.rules)} rules loaded; project {client.project}, location {args.location}")

    if args.dry_run:
        job = client.query(rule_hits_sql(ruleset),
                           job_config=bigquery.QueryJobConfig(dry_run=True))
        print(f"Rule SQL is valid ({job.total_bytes_processed} bytes would be processed).")
        return

    client.query(rule_hits_sql(ruleset)).result()
    client.query(rule_scores_sql(ruleset)).result()
    hits = client.get_table(f"{client.project}.{DATASET_FEATURES}.rule_hits").num_rows
    scores = client.get_table(f"{client.project}.{DATASET_FEATURES}.rule_scores").num_rows
    print(f"Wrote {DATASET_FEATURES}.rule_hits ({hits} rows), "
          f"{DATASET_FEATURES}.rule_scores ({scores} rows)")

    if not args.no_report:
        print_report(client, ruleset)


if __name__ == "__main__":
    main()
