import re

import numpy as np

from fraud_agent.models.claims_model import FEATURES_SQL, threshold_for_precision

LEAKY = ("fraud_flag", "fraud_type", "claim_status", "approved_amount", "policy_status")


def test_feature_sql_has_no_label_or_outcome_columns():
    # Strip comments, which explain the exclusions by name.
    sql = re.sub(r"--[^\n]*", "", FEATURES_SQL.read_text())
    for col in LEAKY:
        assert not re.search(rf"\b{col}\b", sql), col


def test_threshold_for_precision_maximises_recall():
    y = np.array([0, 0, 1, 0, 1, 1])
    score = np.array([0.1, 0.2, 0.3, 0.4, 0.8, 0.9])
    assert threshold_for_precision(y, score, 1.0) == 0.8
    assert threshold_for_precision(y, score, 0.75) == 0.3
