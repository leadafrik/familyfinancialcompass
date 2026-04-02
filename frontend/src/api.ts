import type {
  AnalysisEnvelope,
  AnalyzeRequestPayload,
  CreateScenarioPayload,
  ScenarioEnvelope,
  ScenarioListEnvelope,
} from "./types";

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();

export const apiBaseUrl = configuredBaseUrl && configuredBaseUrl.length > 0 ? configuredBaseUrl.replace(/\/$/, "") : "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Request failed with status ${response.status}`);
  }

  return (await response.json()) as T;
}

export function analyzeRentVsBuy(payload: AnalyzeRequestPayload): Promise<AnalysisEnvelope> {
  return request<AnalysisEnvelope>("/v1/rent-vs-buy/analyze", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function saveRentVsBuyScenario(payload: CreateScenarioPayload): Promise<ScenarioEnvelope> {
  return request<ScenarioEnvelope>("/v1/rent-vs-buy/scenarios", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listScenarios(userId: string): Promise<ScenarioListEnvelope> {
  const query = new URLSearchParams({ limit: "10" });
  return request<ScenarioListEnvelope>(`/v1/users/${encodeURIComponent(userId)}/scenarios?${query.toString()}`);
}
