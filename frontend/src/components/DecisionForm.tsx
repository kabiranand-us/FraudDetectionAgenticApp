import { useEffect, useState } from "react";
import { api } from "../api";
import { DECISION_LABEL } from "./bits";
import type { Alert, DecisionRow } from "../types";

export default function DecisionForm({
  alert,
  pastDecisions,
  onSaved,
}: {
  alert: Alert;
  pastDecisions: DecisionRow[];
  onSaved: () => void;
}) {
  const [types, setTypes] = useState<string[]>([]);
  const [decision, setDecision] = useState("confirmed_fraud");
  const [fraudType, setFraudType] = useState("");
  const [note, setNote] = useState("");
  const [who, setWho] = useState(() => {
    try {
      return localStorage.getItem("investigator") ?? "";
    } catch {
      return "";
    }
  });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.fraudTypes().then((all) => setTypes(all[alert.record_table] ?? [])).catch(() => setTypes([]));
  }, [alert.record_table]);

  useEffect(() => {
    setDecision("confirmed_fraud");
    setFraudType("");
    setNote("");
    setError(null);
  }, [alert.alert_id]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (decision === "confirmed_fraud" && !fraudType) {
      setError("Choose the fraud type you are confirming.");
      return;
    }
    setError(null);
    setSaving(true);
    try {
      await api.decide(alert.alert_id, {
        decision,
        fraud_type: fraudType || null,
        note,
        investigator: who,
      });
      try {
        localStorage.setItem("investigator", who);
      } catch {
        /* private window: the name just isn't remembered */
      }
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="decide" onSubmit={submit} noValidate>
      <strong>Your decision</strong>
      {pastDecisions.length > 0 && (
        <span className="muted">
          Last decision: {DECISION_LABEL[pastDecisions[0].decision] ?? pastDecisions[0].decision} by{" "}
          {pastDecisions[0].investigator ?? "unknown"} on{" "}
          {new Date(pastDecisions[0].decided_at).toLocaleString()}. Saving replaces it.
        </span>
      )}
      <div className="seg" role="radiogroup" aria-label="Decision">
        {Object.entries(DECISION_LABEL).map(([value, label]) => (
          <label key={value}>
            <input
              type="radio"
              name={`decision-${alert.alert_id}`}
              value={value}
              checked={decision === value}
              onChange={() => setDecision(value)}
            />
            <span>{label}</span>
          </label>
        ))}
      </div>
      <div className="form-row">
        <label className="field">
          Fraud type, if confirmed
          <select value={fraudType} onChange={(e) => setFraudType(e.target.value)}>
            <option value="">Choose a type</option>
            {types.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <label className="field">
          Your name
          <input value={who} onChange={(e) => setWho(e.target.value)} />
        </label>
      </div>
      <label className="field">
        Note
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="What you checked and why you decided this."
        />
      </label>
      <div className="form-foot">
        {error ? <span className="error">{error}</span> : <span />}
        <button className="btn primary" type="submit" disabled={saving}>
          {saving ? "Saving…" : "Save decision"}
        </button>
      </div>
    </form>
  );
}
