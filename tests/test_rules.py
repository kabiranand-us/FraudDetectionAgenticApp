import pytest

from fraud_agent.rules.engine import (
    RULES_FILE,
    load_rules,
    rule_hits_sql,
    rule_scores_sql,
)


def test_rules_load_and_validate():
    ruleset = load_rules()
    assert ruleset.rules
    assert {r.table for r in ruleset.rules} == {
        "policies", "claims", "payments", "ghost_broking"
    }


def test_every_rule_in_generated_sql():
    ruleset = load_rules()
    sql = rule_hits_sql(ruleset)
    for rule in ruleset.rules:
        assert f"'{rule.id}' AS rule_id" in sql
    assert sql.count("UNION ALL") == len(ruleset.rules) - 1


def test_scores_cover_all_tables():
    sql = rule_scores_sql(load_rules())
    for table in ("policies", "claims", "payments", "ghost_broking"):
        assert f"FROM fraud_clean.{table}" in sql


@pytest.mark.parametrize("column", ["fraud_flag", "fraud_type", "claim_status", "approved_amount"])
def test_label_columns_rejected(tmp_path, column):
    bad = RULES_FILE.read_text().replace(
        "condition: r.backdated_flag", f"condition: r.{column} IS NOT NULL"
    )
    path = tmp_path / "rules.yaml"
    path.write_text(bad)
    with pytest.raises(ValueError, match=column):
        load_rules(path)
