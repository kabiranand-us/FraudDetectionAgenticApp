import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useJob } from "../useJob";
import JobProgress from "./JobProgress";
import { riskColor } from "./bits";
import type { NetworkDetail } from "../types";

/** Network context for one agent or customer, with the agent's findings when it has run. */
export default function NetworkBox({
  entityId,
  onToast,
}: {
  entityId: string;
  onToast: (message: string) => void;
}) {
  const [detail, setDetail] = useState<NetworkDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setDetail(await api.network(entityId));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [entityId]);

  useEffect(() => {
    setDetail(null);
    setError(null);
    load();
  }, [load]);

  const analysis = useJob(() => {
    onToast(`Network analysis ready for ${entityId}`);
    load();
  });

  if (error) return <div className="error-banner">{error}</div>;
  if (!detail) return <div className="network muted">Loading network for {entityId}…</div>;

  const { network, findings } = detail;
  return (
    <div className="section">
      <h3>Network</h3>
      {findings ? (
        <div className="card">
          <div className="risk-line">
            <span className="mono" style={{ fontWeight: 500 }}>{entityId}</span>
            <strong>{findings.pattern.replace(/_/g, " ")}</strong>
            <span className="risk-big" style={{ fontSize: 15, color: riskColor(findings.risk_level) }}>
              {findings.risk_level}
            </span>
          </div>
          <p style={{ margin: "8px 0" }}>{findings.summary}</p>
          {findings.records_to_review.length > 0 && (
            <p style={{ margin: "0 0 8px" }}>
              <strong>Unflagged records worth reviewing: </strong>
              <span className="mono">{findings.records_to_review.join(", ")}</span>
            </p>
          )}
          <p className="muted" style={{ fontSize: 12, margin: 0 }}>
            A network is a reason to investigate, not proof that each record is fraud.
            {detail.findings_created_at &&
              ` Analysed ${new Date(detail.findings_created_at).toLocaleString()}.`}
          </p>
        </div>
      ) : (
        <div className="network">
          <span>
            <strong className="mono">{entityId}</strong>: {network.risk.alerts} alerts across{" "}
            {network.risk.tables_with_alerts} files ({network.risk.alert_tables.join(", ") || "none"}),{" "}
            {network.unflagged_total} records nothing flagged. The median{" "}
            {network.entity_type} has {network.baseline.median_alerts} alerts.
          </span>
          {analysis.running && analysis.job ? (
            <JobProgress job={analysis.job} fallback={`Analysing ${entityId}`} />
          ) : (
            <button className="btn" onClick={() => analysis.start(() => api.analyseNetwork(entityId))}>
              Analyse network
            </button>
          )}
        </div>
      )}
      {analysis.job?.state === "failed" && (
        <div className="error-banner">Network analysis failed: {analysis.job.detail}</div>
      )}
    </div>
  );
}
