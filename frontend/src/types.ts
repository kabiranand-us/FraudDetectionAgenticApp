export type Severity = "critical" | "high" | "medium" | "low";
export type Status = "open" | "case ready" | "decided";

export interface Alert {
  alert_id: string;
  record_table: string;
  record_id: string;
  priority: number;
  max_severity: Severity;
  alert_source: string;
  rule_ids: string[];
  model_score: number | null;
  agent_id: string;
  customer_id: string | null;
  policy_id: string | null;
  agent_is_hub: boolean;
  customer_is_hub: boolean;
  case_risk: Severity | null;
  review_verdict: string | null;
  decision: string | null;
  status: Status;
}

export interface Evidence { record_id: string; table: string; fact: string }
export interface EvidenceCheck { record_id: string; fact: string; status: string; note: string }
export interface Entity { entity_type: string; entity_id: string; note: string }

export interface CaseFile {
  alert_id: string;
  record_table: string;
  record_id: string;
  why_flagged: string;
  risk_assessment: Severity;
  suspected_fraud_types: string[];
  entities: Entity[];
  evidence: Evidence[];
  mitigating_factors: string[];
  open_questions: string[];
  recommended_action: string;
  recommended_next_steps: string[];
  summary: string;
}

export interface ReviewReport {
  alert_id: string;
  missing_record_ids: string[];
  evidence_checks: EvidenceCheck[];
  issues: string[];
  verdict: string;
  final_risk_assessment: Severity;
  final_recommended_action: string;
  final_suspected_fraud_types: string[];
  reviewer_note: string;
}

export interface RuleHit { rule_id: string; severity: Severity; description: string }

export interface AlertDetail {
  alert: { rule_hits: RuleHit[]; model_score: number | null; [k: string]: unknown };
  record: Record<string, unknown>;
  case: CaseFile | null;
  review: ReviewReport | null;
  case_created_at: string | null;
  agent_model: string | null;
  decisions: DecisionRow[];
}

export interface DecisionRow {
  decided_at: string;
  alert_id?: string;
  decision: string;
  fraud_type: string | null;
  note: string | null;
  investigator: string | null;
}

export interface Hub {
  entity_id: string;
  records: number;
  alerts: number;
  critical_alerts: number;
  tables_with_alerts: number;
  alert_tables: string[];
  flagged_counterparts: number;
  alert_rate: number;
  is_hub: boolean;
}

export interface NetworkFindings {
  entity_id: string;
  entity_type: string;
  pattern: string;
  risk_level: Severity;
  linked_entities: Entity[];
  evidence: Evidence[];
  records_to_review: string[];
  mitigating_factors: string[];
  recommended_action: string;
  summary: string;
}

export interface NetworkDetail {
  network: {
    entity_id: string;
    entity_type: string;
    risk: { alerts: number; tables_with_alerts: number; alert_tables: string[]; is_hub: boolean; records: number };
    unflagged_total: number;
    baseline: { median_alerts: number; note: string };
    connections: { entity_id: string; alerts: number; is_hub: boolean }[];
  };
  findings: NetworkFindings | null;
  findings_created_at: string | null;
}

export interface Job {
  job_id: string;
  state: "running" | "done" | "failed";
  kind: string;
  target: string;
  detail: string;
  stage: string;
  step: string;
  started_at: number;
}
