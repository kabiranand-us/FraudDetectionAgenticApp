import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useJob } from "../useJob";
import DecisionForm from "./DecisionForm";
import JobProgress from "./JobProgress";
// import NetworkBox from "./NetworkBox";
import { ACTION_LABEL, Pill, fileName, riskColor } from "./bits";
import type { Alert, AlertDetail } from "../types";

const CHECK_LABEL: Record<string, string> = {
  verified: "✓ verified",
  unverifiable: "! unverifiable",
  contradicted: "✕ contradicted",
};
const VERDICT_COLOR: Record<string, string> = {
  approved: "var(--verified)",
  approved_with_corrections: "var(--warn)",
  rejected: "var(--bad)",
};
// type Tab = "next" | "questions" | "mitigating";

export default function CasePanel({
  alert,
  onDecision,
  onCaseWritten,
  onToast,
}: {
  alert: Alert;
  onDecision: (message: string) => void;
  onCaseWritten: () => void;
  onToast: (message: string) => void;
}) {
  const [detail, setDetail] = useState<AlertDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  // const [tab, setTab] = useState<Tab>("next");

  const load = useCallback(async () => {
    try {
      setDetail(await api.alert(alert.alert_id));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [alert.alert_id]);

  useEffect(() => {
    setDetail(null);
    setError(null);
    // setTab("next");
    load();
  }, [load]);

  const investigation = useJob(() => {
    onToast(`Case ready for ${alert.record_id}`);
    load();
    onCaseWritten();
  });

  if (error) return <div className="case"><div className="error-banner">{error}</div></div>;
  if (!detail) return <div className="case"><div className="loading">Loading case…</div></div>;

  const { alert: info, case: file, review } = detail;
  // const hubs = [
  //   alert.agent_is_hub ? "agent" : null,
  //   alert.customer_is_hub ? "customer" : null,
  // ].filter(Boolean);

  const head = (
    <div className="case-head">
      <div>
        <h2>
          <span className="mono" style={{ fontSize: 18 }}>{alert.record_id}</span>
          <Pill level={alert.max_severity} />
          <span className="muted" style={{ fontSize: 14, fontWeight: 400 }}>
            {fileName(alert.record_table)}
          </span>
        </h2>
        <div className="facts">
          <span>priority <b>{alert.priority.toFixed(2)}</b></span>
          <span>source <b>{alert.alert_source}</b></span>
          <span>agent <b className="mono">{alert.agent_id}</b></span>
          {alert.customer_id && <span>customer <b className="mono">{alert.customer_id}</b></span>}
          {alert.policy_id && <span>policy <b className="mono">{alert.policy_id}</b></span>}
          {/* {hubs.length > 0 && <span className="hub">● network hub: {hubs.join(", ")}</span>} */}
        </div>
      </div>
    </div>
  );

  const flagged = (
    <div className="card">
      <h3>Why it was flagged</h3>
      <ul className="clean flagged-by">
        {info.rule_hits.map((h) => (
          <li key={h.rule_id}>
            <Pill level={h.severity} />
            <span>
              <span className="mono">{h.rule_id}</span> · {h.description}
            </span>
          </li>
        ))}
        {info.model_score != null && (
          <li>
            <span className="pill sev-medium">model</span>
            <span>Claims model score {info.model_score.toFixed(2)} (0 to 1)</span>
          </li>
        )}
      </ul>
    </div>
  );

  if (!file) {
    return (
      <div className="case">
        {head}
        {flagged}
        {investigation.job?.state === "failed" && (
          <div className="error-banner">Investigation failed: {investigation.job.detail}</div>
        )}
        {investigation.running && investigation.job ? (
          <JobProgress job={investigation.job} fallback={`Investigating ${alert.record_id}`} />
        ) : (
          <div className="no-case">
            <strong>No case file yet</strong>
            <span className="muted">
              The agents investigate this alert, write a case and have it reviewed. This usually
              takes 1 to 3 minutes, longer when Vertex AI throttles the requests.
            </span>
            <button
              className="btn primary"
              onClick={() => investigation.start(() => api.investigate(alert.alert_id))}
            >
              Investigate now
            </button>
          </div>
        )}
      </div>
    );
  }

  const finalRisk = review?.final_risk_assessment ?? file.risk_assessment;
  const finalAction = review?.final_recommended_action ?? file.recommended_action;
  const finalTypes = review?.final_suspected_fraud_types ?? file.suspected_fraud_types;
  // const tabs: Record<Tab, [string, string[]]> = {
  //   next: ["Next steps", file.recommended_next_steps],
  //   questions: ["Open questions", file.open_questions],
  //   mitigating: ["Mitigating factors", file.mitigating_factors],
  // };

  return (
    <div className="case">
      {head}

      <div className="verdict">
        <div className="card">
          <h3>Assessment after review</h3>
          <div className="risk-line">
            <span className="risk-big" style={{ color: riskColor(finalRisk) }}>{finalRisk}</span>
            {review && finalRisk !== file.risk_assessment && (
              <span className="muted">corrected from {file.risk_assessment}</span>
            )}
          </div>
          <dl className="kv">
            <dt>Action</dt>
            <dd>{ACTION_LABEL[finalAction] ?? finalAction}</dd>
            <dt>Fraud types</dt>
            <dd>{finalTypes.length ? finalTypes.join(", ") : <span className="muted">none on this record</span>}</dd>
          </dl>
          <p style={{ margin: "10px 0 0" }}>{file.summary}</p>
        </div>

        <div className="card">
          <h3>Reviewer</h3>
          {review ? (
            <>
              <div className="review-badge" style={{ color: VERDICT_COLOR[review.verdict] ?? "var(--ink)" }}>
                ● {review.verdict.replace(/_/g, " ")}
              </div>
              <p style={{ margin: "6px 0 10px" }}>{review.reviewer_note}</p>
              {review.missing_record_ids.length > 0 && (
                <div className="error-banner">
                  Cited IDs not found in the data: {review.missing_record_ids.join(", ")}
                </div>
              )}
              {review.issues.map((issue, i) => (
                <p key={i} style={{ color: "var(--warn)", margin: "6px 0 0" }}>{issue}</p>
              ))}
            </>
          ) : (
            <p className="muted" style={{ margin: 0 }}>
              This case was written before the reviewer existed; its evidence is unchecked.
            </p>
          )}
          {detail.case_created_at && (
            <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>
              Written {new Date(detail.case_created_at).toLocaleString()} by {detail.agent_model}.
            </p>
          )}
        </div>
      </div>

      {flagged}

      <div className="section">
        <h3>Evidence{review ? ", checked against the data" : ""}</h3>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {review && <th>Check</th>}
                <th>Record</th>
                <th>Fact in the case</th>
                {review && <th>What the data shows</th>}
              </tr>
            </thead>
            <tbody>
              {review
                ? review.evidence_checks.map((e, i) => (
                    <tr key={i}>
                      <td className={`check ${e.status}`}>{CHECK_LABEL[e.status] ?? e.status}</td>
                      <td className="mono">{e.record_id}</td>
                      <td>{e.fact}</td>
                      <td className="muted">{e.note}</td>
                    </tr>
                  ))
                : file.evidence.map((e, i) => (
                    <tr key={i}>
                      <td className="mono">{e.record_id}</td>
                      <td>{e.fact}</td>
                    </tr>
                  ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 
      <div className="section">
        <div className="tabs" role="tablist">
          {(Object.entries(tabs) as [Tab, [string, string[]]][]).map(([key, [label]]) => (
            <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>
              {label}
            </button>
          ))}
        </div>
        <div className="tab-body" role="tabpanel">
          {tabs[tab][1].length ? (
            <ul>{tabs[tab][1].map((item, i) => <li key={i}>{item}</li>)}</ul>
          ) : (
            <p className="muted">None.</p>
          )}
        </div>
      </div>
      */}

      {file.entities.length > 0 && (
        <div className="section">
          <h3>People and policies involved</h3>
          <div className="entities">
            {file.entities.map((e, i) => (
              <div className="entity" key={i}>
                <div className="kind">{e.entity_type}</div>
                <div className="mono" style={{ fontWeight: 500 }}>{e.entity_id}</div>
                <div className="muted">{e.note}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* {alert.agent_is_hub && <NetworkBox entityId={alert.agent_id} onToast={onToast} />} */}
      {/* {alert.customer_is_hub && alert.customer_id && (
        <NetworkBox entityId={alert.customer_id} onToast={onToast} />
      )} */}

      <details className="raw">
        <summary>Raw record</summary>
        <pre className="json-block">{JSON.stringify(detail.record, null, 2)}</pre>
      </details>

      <DecisionForm
        alert={alert}
        pastDecisions={detail.decisions}
        onSaved={async () => {
          await load();
          onDecision(`Decision saved for ${alert.record_id}`);
        }}
      />
    </div>
  );
}
