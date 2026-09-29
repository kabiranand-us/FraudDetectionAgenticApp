import { useMemo, useState } from "react";
import CasePanel from "./CasePanel";
import { Metric, Pill, fileName } from "./bits";
import type { Alert, Status } from "../types";

const STATUSES: Status[] = ["open", "case ready", "decided"];
const TABLES = ["all", "claims", "policies", "payments", "ghost_broking"];

export default function Queue({
  alerts,
  onDecision,
  onCaseWritten,
  onToast,
}: {
  alerts: Alert[] | null;
  onDecision: (message: string) => void;
  onCaseWritten: () => void;
  onToast: (message: string) => void;
}) {
  const [status, setStatus] = useState<Set<Status>>(new Set(["open", "case ready"]));
  const [table, setTable] = useState("all");
  // const [hubOnly, setHubOnly] = useState(false);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);

  const rows = useMemo(() => {
    const q = query.trim().toUpperCase();
    return (alerts ?? []).filter(
      (a) =>
        status.has(a.status) &&
        (table === "all" || a.record_table === table) &&
        // (!hubOnly || a.agent_is_hub || a.customer_is_hub) &&
        (!q ||
          [a.record_id, a.agent_id, a.customer_id].some((v) => v?.toUpperCase().includes(q))),
    );
  }, [alerts, status, table, query]);

  const open = alerts?.find((a) => a.alert_id === selected) ?? null;
  const counts = (s: Status) => (alerts ?? []).filter((a) => a.status === s).length;
  const total = alerts?.length ?? 0;

  const toggleStatus = (s: Status) => {
    const next = new Set(status);
    next.has(s) ? next.delete(s) : next.add(s);
    setStatus(next);
  };

  return (
    <>
      <div className="topbar">
        <div>
          <h1>Alert queue</h1>
          <p className="subtitle">Highest priority first. Select an alert to open its case.</p>
        </div>
      </div>

      <section className="metrics" aria-label="Queue summary">
        <Metric label="Alerts" value={total} share={100} />
        <Metric label="Open" value={counts("open")} share={total ? (counts("open") / total) * 100 : 0} />
        <Metric label="Case ready" value={counts("case ready")} share={total ? (counts("case ready") / total) * 100 : 0} />
        <Metric label="Decided" value={counts("decided")} share={total ? (counts("decided") / total) * 100 : 0} />
      </section>

      <div className="split">
        <section className="panel" aria-label="Alerts">
          <div className="filters">
            <label className="search">
              <span aria-hidden="true">⌕</span>
              <input
                placeholder="Record, agent or customer ID"
                aria-label="Search alerts"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
            {STATUSES.map((s) => (
              <button key={s} className="chip" aria-pressed={status.has(s)} onClick={() => toggleStatus(s)}>
                {s}
              </button>
            ))}
            <span style={{ flexBasis: "100%", height: 0 }} />
            {TABLES.map((t) => (
              <button key={t} className="chip" aria-pressed={table === t} onClick={() => setTable(t)}>
                {t === "all" ? "all files" : fileName(t)}
              </button>
            ))}
            {/* <button className="chip" aria-pressed={hubOnly} onClick={() => setHubOnly(!hubOnly)}>
              network hubs
            </button> */}
          </div>

          <div className="list" role="listbox" aria-label="Alert list">
            {!alerts &&
              Array.from({ length: 6 }, (_, i) => <div className="skeleton" key={i} />)}
            {alerts && rows.length === 0 && (
              <div className="empty">No alerts match these filters.</div>
            )}
            {rows.slice(0, 300).map((a) => (
              <div
                key={a.alert_id}
                className="row"
                role="option"
                tabIndex={0}
                aria-selected={a.alert_id === selected}
                onClick={() => setSelected(a.alert_id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setSelected(a.alert_id);
                  }
                }}
              >
                <span className={`stripe sev-${a.max_severity}`} />
                <div>
                  <div className="top">
                    <span className="rid">{a.record_id}</span>
                    <Pill level={a.max_severity} />
                    {/* {(a.agent_is_hub || a.customer_is_hub) && <span className="hub">● hub agent</span>} */}
                  </div>
                  <div className="meta">
                    {fileName(a.record_table)} · {a.alert_source} · agent{" "}
                    <span className="mono">{a.agent_id}</span>
                  </div>
                </div>
                <div className="side">
                  <span
                    className={`status ${a.status === "case ready" ? "ready" : a.status === "decided" ? "decided" : ""}`}
                  >
                    {a.status}
                  </span>
                  <span>priority {a.priority.toFixed(2)}</span>
                </div>
              </div>
            ))}
            {rows.length > 300 && (
              <div className="empty">
                Showing the first 300 of {rows.length}. Narrow the filters to see the rest.
              </div>
            )}
          </div>
        </section>

        <section className="panel" aria-label="Case">
          {open ? (
            <CasePanel
              alert={open}
              onDecision={onDecision}
              onCaseWritten={onCaseWritten}
              onToast={onToast}
            />
          ) : (
            <div className="case">
              <p className="muted">Select an alert to open its case.</p>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
