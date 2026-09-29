import { useState } from "react";
import NetworkBox from "./NetworkBox";
import type { Hub } from "../types";

export default function Networks({
  hubs,
  onToast,
}: {
  hubs: Hub[] | null;
  onToast: (message: string) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  if (!hubs) return <div className="loading">Loading networks…</div>;
  const widest = Math.max(1, ...hubs.map((h) => h.alerts));

  return (
    <>
      <div className="topbar">
        <div>
          <h1>Networks</h1>
          <p className="subtitle">
            Agents most strongly tied to alerts, from rules and the model only.
          </p>
        </div>
      </div>
      <p className="note">
        A hub has at least 5 alerts across at least 2 files. Records of hub agents that nothing
        flagged are fraud 12.3% of the time, against 2.8% for other agents.
      </p>
      <section className="panel">
        <div className="table-wrap" style={{ border: 0 }}>
          <table>
            <thead>
              <tr>
                <th>Agent</th>
                <th>Records</th>
                <th>Alerts</th>
                <th>Critical</th>
                <th>Files with alerts</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {hubs.map((h) => (
                <tr key={h.entity_id}>
                  <td className="mono">
                    {h.entity_id} {h.is_hub && <span className="hub">● hub</span>}
                  </td>
                  <td>{h.records}</td>
                  <td>
                    <span className="bar-cell">
                      <i style={{ width: `${(h.alerts / widest) * 90}px` }} />
                      {h.alerts}
                    </span>
                  </td>
                  <td>{h.critical_alerts}</td>
                  <td className="muted">{h.alert_tables.join(", ")}</td>
                  <td>
                    <button className="btn" onClick={() => setSelected(h.entity_id)}>
                      Open
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {selected && (
        <section className="panel">
          <div className="case">
            <NetworkBox entityId={selected} onToast={onToast} />
          </div>
        </section>
      )}
    </>
  );
}
