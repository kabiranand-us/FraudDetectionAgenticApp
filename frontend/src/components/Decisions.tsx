import { DECISION_LABEL, Metric } from "./bits";
import type { DecisionRow } from "../types";

export default function Decisions({ decisions }: { decisions: DecisionRow[] | null }) {
  if (!decisions) return <div className="loading">Loading decisions…</div>;
  const count = (key: string) => decisions.filter((d) => d.decision === key).length;
  return (
    <>
      <div className="topbar">
        <div>
          <h1>Decisions</h1>
          <p className="subtitle">Investigator decisions become the new labels for retraining.</p>
        </div>
      </div>
      <section className="metrics" style={{ gridTemplateColumns: "repeat(3,minmax(0,1fr))" }}>
        {Object.entries(DECISION_LABEL).map(([key, label]) => (
          <Metric key={key} label={label} value={count(key)} />
        ))}
      </section>
      <section className="panel">
        <div className="table-wrap" style={{ border: 0 }}>
          <table>
            <thead>
              <tr>
                <th>Decided</th>
                <th>Alert</th>
                <th>Decision</th>
                <th>Fraud type</th>
                <th>Note</th>
                <th>Investigator</th>
              </tr>
            </thead>
            <tbody>
              {decisions.length === 0 && (
                <tr>
                  <td colSpan={6} className="muted">
                    No decisions yet. Open a case in the queue to record one.
                  </td>
                </tr>
              )}
              {decisions.map((d, i) => (
                <tr key={i}>
                  <td>{new Date(d.decided_at).toLocaleString()}</td>
                  <td className="mono">{d.alert_id}</td>
                  <td>{DECISION_LABEL[d.decision] ?? d.decision}</td>
                  <td>{d.fraud_type ?? "—"}</td>
                  <td>{d.note ?? "—"}</td>
                  <td>{d.investigator ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
