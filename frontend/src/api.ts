import type { Alert, AlertDetail, DecisionRow, Hub, Job, NetworkDetail } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  alerts: () => request<Alert[]>("/alerts"),
  alert: (id: string) => request<AlertDetail>(`/alerts/${encodeURIComponent(id)}`),
  investigate: (id: string) => request<Job>(`/alerts/${encodeURIComponent(id)}/investigate`, { method: "POST" }),
  networks: (limit = 50) => request<Hub[]>(`/networks?limit=${limit}`),
  network: (entityId: string) => request<NetworkDetail>(`/networks/${encodeURIComponent(entityId)}`),
  analyseNetwork: (entityId: string) =>
    request<Job>(`/networks/${encodeURIComponent(entityId)}/analyse`, { method: "POST" }),
  job: (jobId: string) => request<Job>(`/jobs/${jobId}`),
  decisions: () => request<DecisionRow[]>("/decisions"),
  fraudTypes: () => request<Record<string, string[]>>("/fraud-types"),
  decide: (id: string, body: { decision: string; fraud_type: string | null; note: string; investigator: string }) =>
    request<{ saved: boolean }>(`/alerts/${encodeURIComponent(id)}/decision`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
