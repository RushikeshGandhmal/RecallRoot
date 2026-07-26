import {
  asRecord,
  normalizeComparison,
  normalizeGraph,
  normalizeHealth,
  normalizeIncident,
  normalizeIncidentList,
  normalizeInvestigation,
  normalizeReadiness,
} from "./normalize";
import type {
  CausalGraph,
  DemoProgress,
  DemoStep,
  HealthStatus,
  Incident,
  Investigation,
  ReadinessStatus,
  ReplayComparison,
} from "./types";

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/recallroot").replace(/\/$/, "");
const DEFAULT_TIMEOUT_MS = 15_000;
const EVIDENCE_SYNC_ATTEMPTS = 6;
const EVIDENCE_SYNC_DELAY_MS = 1_500;

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  timeoutMs?: number;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly details?: unknown;

  constructor(message: string, status: number, details?: unknown, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
    this.code = code;
  }
}

async function request(path: string, options: RequestOptions = {}): Promise<unknown> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  const headers = new Headers(options.headers);
  if (options.body !== undefined) headers.set("Content-Type", "application/json");
  headers.set("Accept", "application/json");

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      headers,
      cache: "no-store",
      signal: controller.signal,
    });
    const contentType = response.headers.get("content-type") ?? "";
    const payload: unknown = contentType.includes("application/json")
      ? await response.json()
      : await response.text();

    if (!response.ok) {
      const record = asRecord(payload);
      const detail = record.detail;
      const detailRecord = asRecord(detail);
      const message =
        typeof detail === "string"
          ? detail
          : typeof detailRecord.message === "string"
            ? detailRecord.message
          : typeof record.message === "string"
            ? record.message
            : `Request failed with status ${response.status}`;
      const code = typeof detailRecord.code === "string"
        ? detailRecord.code
        : typeof record.code === "string"
          ? record.code
          : undefined;
      throw new ApiError(message, response.status, payload, code);
    }
    return payload;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("The RecallRoot API took too long to respond.", 408, undefined, "request_timeout");
    }
    throw new ApiError(
      "Unable to reach the RecallRoot API. Confirm the backend is running and try again.",
      0,
      error,
      "network_error",
    );
  } finally {
    clearTimeout(timeout);
  }
}

function post(path: string, body?: unknown, timeoutMs?: number): Promise<unknown> {
  return request(path, { method: "POST", body, timeoutMs });
}

function isLiveEvidence(graph: CausalGraph): boolean {
  return !graph.source.toLowerCase().replace(/[ .-]+/g, "_").includes("local_evidence");
}

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

export const api = {
  async health(): Promise<HealthStatus> {
    return normalizeHealth(await request("/health"));
  },

  async readiness(): Promise<ReadinessStatus> {
    return normalizeReadiness(await request("/ready", { timeoutMs: 8_000 }));
  },

  async listIncidents(): Promise<Incident[]> {
    return normalizeIncidentList(await request("/incidents"));
  },

  async getIncident(id: string): Promise<Incident> {
    return normalizeIncident(await request(`/incidents/${encodeURIComponent(id)}`));
  },

  async getGraph(id: string): Promise<CausalGraph> {
    return normalizeGraph(await request(`/incidents/${encodeURIComponent(id)}/graph`, { timeoutMs: 25_000 }));
  },

  async waitForSignozGraph(id: string, initial?: CausalGraph): Promise<CausalGraph> {
    let latest = initial;
    for (let attempt = 0; attempt < EVIDENCE_SYNC_ATTEMPTS; attempt += 1) {
      if (latest && isLiveEvidence(latest)) return latest;
      if (attempt > 0 || latest) await wait(EVIDENCE_SYNC_DELAY_MS);
      latest = await api.getGraph(id);
    }
    return latest ?? api.getGraph(id);
  },

  async investigate(id: string): Promise<Investigation> {
    return normalizeInvestigation(
      await post(`/incidents/${encodeURIComponent(id)}/investigate`, undefined, 45_000),
    );
  },

  async quarantineMemory(id: string): Promise<unknown> {
    return post(`/memories/${encodeURIComponent(id)}/quarantine`);
  },

  async replayIncident(id: string): Promise<ReplayComparison> {
    const result = await post(`/incidents/${encodeURIComponent(id)}/replay`, undefined, 30_000);
    const record = asRecord(result);
    const hasComparison = record.original || record.before || record.replay || record.after || record.comparison;
    if (hasComparison) return normalizeComparison(result, id);
    return api.getComparison(id);
  },

  async getComparison(id: string): Promise<ReplayComparison> {
    return normalizeComparison(
      await request(`/incidents/${encodeURIComponent(id)}/comparison`),
      id,
    );
  },

  async resetDemo(): Promise<unknown> {
    return post("/demo/reset");
  },

  async seedTrustedPolicy(): Promise<unknown> {
    return post("/demo/seed-trusted-policy");
  },

  async ingestUnsafeMemory(): Promise<unknown> {
    return post("/demo/ingest-unsafe-memory");
  },

  async requestRefund(): Promise<unknown> {
    return post("/agent/refund", {
      customer_id: "demo-customer",
      amount: 35_000,
      reason: "Duplicate charge",
    });
  },

  async runDemoScenario(onProgress?: (progress: DemoProgress[]) => void): Promise<string> {
    const order: DemoStep[] = ["reset", "policy", "memory", "incident", "telemetry"];
    const states = new Map<DemoStep, DemoProgress["state"]>(order.map((step) => [step, "pending"]));
    const notify = () =>
      onProgress?.(order.map((step) => ({ step, state: states.get(step) ?? "pending" })));
    const execute = async (step: DemoStep, operation: () => Promise<unknown>) => {
      states.set(step, "running");
      notify();
      const result = await operation();
      states.set(step, "complete");
      notify();
      return result;
    };

    notify();
    await execute("reset", api.resetDemo);
    await execute("policy", api.seedTrustedPolicy);
    await execute("memory", api.ingestUnsafeMemory);
    const refund = await execute("incident", api.requestRefund);
    const refundRecord = asRecord(refund);
    const nestedIncident = asRecord(refundRecord.incident);
    const incidentId =
      (typeof refundRecord.incident_id === "string" && refundRecord.incident_id) ||
      (typeof nestedIncident.incident_id === "string" && nestedIncident.incident_id) ||
      (typeof nestedIncident.id === "string" && nestedIncident.id);
    const resolvedIncidentId = incidentId || (await api.listIncidents())[0]?.id;
    if (!resolvedIncidentId) {
      throw new ApiError("The scenario completed without creating an incident.", 500);
    }
    await execute("telemetry", () => api.waitForSignozGraph(resolvedIncidentId));
    return resolvedIncidentId;
  },
};
