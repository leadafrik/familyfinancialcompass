import type {
  AnalysisEnvelope,
  AnalyzeRequestPayload,
  CollegeVsRetirementAnalysisEnvelope,
  CollegeVsRetirementInputPayload,
  CollegeVsRetirementReport,
  CurrentAssumptionsEnvelope,
  CreateScenarioPayload,
  JobOfferAnalysisEnvelope,
  JobOfferInputPayload,
  JobOfferReport,
  ReportEnvelope,
  RetirementAnalysisEnvelope,
  RetirementInputPayload,
  RetirementSurvivalReport,
  ScenarioEnvelope,
  ScenarioListEnvelope,
} from "./types";

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();

export const apiBaseUrl = configuredBaseUrl && configuredBaseUrl.length > 0 ? configuredBaseUrl.replace(/\/$/, "") : "/api";

/**
 * Endpoint access token — prevents anonymous internet bots from hitting the API.
 * This is NOT the user-data security boundary: per-user data isolation is enforced
 * server-side by requiring and verifying user_id on every scenario read.
 * Public browser builds should leave VITE_ENABLE_SAVED_ANALYSES disabled.
 */
const SAVED_ANALYSES_ENABLED = ["1", "true", "yes", "on"].includes(
  (import.meta.env.VITE_ENABLE_SAVED_ANALYSES ?? "").trim().toLowerCase(),
);
const API_KEY = SAVED_ANALYSES_ENABLED ? import.meta.env.VITE_API_KEY?.trim() ?? "" : "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const extraHeaders: Record<string, string> = {};
  if (API_KEY) {
    extraHeaders["X-API-Key"] = API_KEY;
  }
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...extraHeaders,
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

export function analyzeRetirementSurvival(payload: {
  input: RetirementInputPayload;
  simulation_seed: number;
}): Promise<RetirementAnalysisEnvelope> {
  return request<RetirementAnalysisEnvelope>("/v1/retirement-survival/analyze", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function analyzeCollegeVsRetirement(payload: {
  input: CollegeVsRetirementInputPayload;
  simulation_seed: number;
}): Promise<CollegeVsRetirementAnalysisEnvelope> {
  return request<CollegeVsRetirementAnalysisEnvelope>("/v1/college-vs-retirement/analyze", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function analyzeJobOffer(payload: {
  input: JobOfferInputPayload;
  simulation_seed: number;
}): Promise<JobOfferAnalysisEnvelope> {
  return request<JobOfferAnalysisEnvelope>("/v1/job-offer/analyze", {
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

export function saveRetirementSurvivalScenario(payload: {
  input: RetirementInputPayload;
  simulation_seed: number;
  user_id?: string | null;
  idempotency_key?: string | null;
}): Promise<ScenarioEnvelope> {
  return request<ScenarioEnvelope>("/v1/retirement-survival/scenarios", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function saveJobOfferScenario(payload: {
  input: JobOfferInputPayload;
  simulation_seed: number;
  user_id?: string | null;
  idempotency_key?: string | null;
}): Promise<ScenarioEnvelope> {
  return request<ScenarioEnvelope>("/v1/job-offer/scenarios", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function saveCollegeVsRetirementScenario(payload: {
  input: CollegeVsRetirementInputPayload;
  simulation_seed: number;
  user_id?: string | null;
  idempotency_key?: string | null;
}): Promise<ScenarioEnvelope> {
  return request<ScenarioEnvelope>("/v1/college-vs-retirement/scenarios", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getScenario(scenarioId: string, userId: string): Promise<ScenarioEnvelope> {
  const query = `?user_id=${encodeURIComponent(userId)}`;
  return request<ScenarioEnvelope>(`/v1/scenarios/${encodeURIComponent(scenarioId)}${query}`);
}

export function buildRentVsBuyReport(payload: AnalyzeRequestPayload): Promise<ReportEnvelope> {
  return request<ReportEnvelope>("/v1/rent-vs-buy/report", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function buildRetirementSurvivalReport(payload: {
  input: RetirementInputPayload;
  simulation_seed: number;
}): Promise<ReportEnvelope<RetirementSurvivalReport>> {
  return request<ReportEnvelope<RetirementSurvivalReport>>("/v1/retirement-survival/report", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function buildJobOfferReport(payload: {
  input: JobOfferInputPayload;
  simulation_seed: number;
}): Promise<ReportEnvelope<JobOfferReport>> {
  return request<ReportEnvelope<JobOfferReport>>("/v1/job-offer/report", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function buildCollegeVsRetirementReport(payload: {
  input: CollegeVsRetirementInputPayload;
  simulation_seed: number;
}): Promise<ReportEnvelope<CollegeVsRetirementReport>> {
  return request<ReportEnvelope<CollegeVsRetirementReport>>("/v1/college-vs-retirement/report", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getCurrentRentVsBuyAssumptions(): Promise<CurrentAssumptionsEnvelope> {
  return request<CurrentAssumptionsEnvelope>("/v1/rent-vs-buy/assumptions/current");
}

export function listScenarios(userId: string): Promise<ScenarioListEnvelope> {
  const query = new URLSearchParams({ limit: "10" });
  return request<ScenarioListEnvelope>(`/v1/users/${encodeURIComponent(userId)}/scenarios?${query.toString()}`);
}
