import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import Queue from "./components/Queue";
import Networks from "./components/Networks";
import Decisions from "./components/Decisions";
import Toast from "./components/Toast";
import type { Alert, DecisionRow, Hub } from "./types";

type View = "queue" | "networks" | "decisions";

function useTheme() {
  const [theme, setTheme] = useState<"light" | "dark" | null>(() => {
    try {
      return (localStorage.getItem("theme") as "light" | "dark" | null) ?? null;
    } catch {
      return null;
    }
  });
  useEffect(() => {
    if (theme) document.documentElement.dataset.theme = theme;
    else delete document.documentElement.dataset.theme;
    try {
      theme ? localStorage.setItem("theme", theme) : localStorage.removeItem("theme");
    } catch {
      /* private window: the page still works, the choice just isn't remembered */
    }
  }, [theme]);
  const toggle = () => {
    const isDark = theme
      ? theme === "dark"
      : window.matchMedia("(prefers-color-scheme: dark)").matches;
    setTheme(isDark ? "light" : "dark");
  };
  return toggle;
}

export default function App() {
  const [view, setView] = useState<View>("queue");
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [hubs, setHubs] = useState<Hub[] | null>(null);
  const [decisions, setDecisions] = useState<DecisionRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const toggleTheme = useTheme();

  const loadAlerts = useCallback(async () => {
    try {
      setAlerts(await api.alerts());
    } catch (e) {
      setError(`Could not load alerts: ${(e as Error).message}`);
    }
  }, []);
  const loadDecisions = useCallback(async () => {
    try {
      setDecisions(await api.decisions());
    } catch (e) {
      setError(`Could not load decisions: ${(e as Error).message}`);
    }
  }, []);

  useEffect(() => {
    loadAlerts();
    loadDecisions();
    api.networks().then(setHubs).catch((e) => setError(`Could not load networks: ${e.message}`));
  }, [loadAlerts, loadDecisions]);

  const counts = {
    queue: alerts?.length ?? 0,
    networks: hubs?.filter((h) => h.is_hub).length ?? 0,
    decisions: decisions?.length ?? 0,
  };

  const afterDecision = async (message: string) => {
    setToast(message);
    await Promise.all([loadAlerts(), loadDecisions()]);
  };

  return (
    <div className="shell">
      <aside className="rail" aria-label="Main navigation">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">◆</span>Fraud Investigations
        </div>
        <nav className="nav">
          {(
            [
              ["queue", "Alert queue", counts.queue],
              ["decisions", "Decisions", counts.decisions],
            ] as const
          ).map(([key, label, count]) => (
            <button
              key={key}
              onClick={() => setView(key)}
              aria-current={view === key ? "page" : undefined}
            >
              {label} <span className="count">{count}</span>
            </button>
          ))}
        </nav>
        <div className="rail-foot">
          <span>Signed in as investigator</span>
          <button className="theme-toggle" type="button" onClick={toggleTheme}>
            Switch theme
          </button>
        </div>
      </aside>

      <main className="main">
        {error && <div className="error-banner">{error}</div>}
        {view === "queue" && (
          <Queue
            alerts={alerts}
            onDecision={afterDecision}
            onCaseWritten={loadAlerts}
            onToast={setToast}
          />
        )}
        {view === "networks" && <Networks hubs={hubs} onToast={setToast} />}
        {view === "decisions" && <Decisions decisions={decisions} />}
      </main>
      <Toast message={toast} onDone={() => setToast(null)} />
    </div>
  );
}
