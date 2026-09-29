import type { Severity } from "../types";

export const fileName = (table: string) => table.replace("_", " ");

export const ACTION_LABEL: Record<string, string> = {
  reject_and_refer_to_siu: "Reject and refer to the Special Investigations Unit",
  hold_for_investigation: "Hold for investigation",
  request_documents: "Request documents",
  approve: "Approve",
};

export const DECISION_LABEL: Record<string, string> = {
  confirmed_fraud: "Confirm fraud",
  not_fraud: "Not fraud",
  needs_more_info: "Needs more information",
};

export function Pill({ level }: { level: string }) {
  return <span className={`pill sev-${level}`}>{level}</span>;
}

export function Metric({ label, value, share }: { label: string; value: number; share?: number }) {
  return (
    <div className="metric">
      <div className="label">{label}</div>
      <div className="value">{value.toLocaleString()}</div>
      {share !== undefined && (
        <div className="bar">
          <i style={{ width: `${Math.min(100, share)}%` }} />
        </div>
      )}
    </div>
  );
}

export function riskColor(level: Severity | string) {
  return `var(--${level})`;
}

export function Spinner() {
  return <span className="spinner" aria-hidden="true" />;
}
