export type RiskLevel = "low" | "medium" | "high" | "critical";

export type IncidentStatus = "open" | "investigating" | "remediated" | "closed";

export interface RiskFactor {
  label: string;
  points: number;
  detail?: string;
}

export interface IncidentAction {
  id?: string;
  type: string;
  amount: number;
  customerId?: string;
  sensitivity?: string;
  approvalRequired?: boolean;
  approvalPresent?: boolean;
  outcome?: string;
  traceId?: string;
  spanId?: string;
  decisionProvider?: string;
  decisionModel?: string;
  decisionFallback?: boolean;
  decisionFallbackReason?: string;
}

export interface IncidentMemory {
  id: string;
  content?: string;
  sourceName: string;
  sourceType?: string;
  sourceTrust: string;
  status: string;
  createdAt?: string;
  retrievalCount?: number;
  originTraceId?: string;
  originSpanId?: string;
}

export interface Incident {
  id: string;
  title: string;
  status: IncidentStatus;
  riskScore: number;
  riskLevel: RiskLevel;
  riskFactors: RiskFactor[];
  policyOutcome: string;
  summary?: string;
  detectedAt?: string;
  sessionId?: string;
  action: IncidentAction;
  memory: IncidentMemory;
}

export type CausalNodeKind =
  | "source"
  | "memory_write"
  | "memory"
  | "memory_use"
  | "decision"
  | "action"
  | "outcome"
  | "unknown";

export interface GraphLog {
  timestamp?: string;
  severity?: string;
  body: string;
  attributes?: Record<string, unknown>;
}

export interface CausalGraphNode {
  id: string;
  kind: CausalNodeKind;
  label: string;
  description?: string;
  session?: string;
  status?: string;
  timestamp?: string;
  traceId?: string;
  spanId?: string;
  evidenceUrl?: string;
  attributes: Record<string, unknown>;
  logs: GraphLog[];
  position?: { x: number; y: number };
}

export interface CausalGraphEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  kind: "parent_child" | "cross_trace" | "causal";
}

export interface GraphEvidence {
  id: string;
  nodeId?: string;
  title: string;
  detail: string;
  kind?: string;
  timestamp?: string;
  traceId?: string;
  spanId?: string;
  signozUrl?: string;
  attributes?: Record<string, unknown>;
}

export interface CausalGraph {
  nodes: CausalGraphNode[];
  edges: CausalGraphEdge[];
  evidence: GraphEvidence[];
  source: string;
  warnings: string[];
  generatedAt?: string;
}

export interface Investigation {
  summary: string;
  explanation?: string;
  findings: string[];
  evidence: GraphEvidence[];
  source: string;
  warnings: string[];
  investigatedAt?: string;
}

export interface ComparisonSide {
  label: string;
  memoryId?: string;
  memoryStatus: string;
  memoryTrust: string;
  memoryContent?: string;
  decision: string;
  tool: string;
  policyOutcome: string;
  riskScore: number;
  traceId?: string;
  createdAt?: string;
}

export interface CausalMemoryRemediation {
  id?: string;
  sourceTrust: string;
  beforeStatus: string;
  afterStatus: string;
  remediation: string;
}

export interface OperativeReplayMemory {
  id?: string;
  sourceTrust: string;
  status: string;
}

export interface ReplayComparison {
  incidentId: string;
  replayId?: string;
  result: string;
  verified: boolean;
  original: ComparisonSide;
  replay: ComparisonSide;
  causalMemory: CausalMemoryRemediation;
  operativeReplayMemory: OperativeReplayMemory;
  explanation?: string;
  verifiedAt?: string;
  createdAt?: string;
}

export interface HealthStatus {
  status: string;
  service?: string;
  telemetry?: string;
}

export type ReadinessState = "ready" | "degraded" | "unconfigured" | "unavailable";

export interface ReadinessCheck {
  status: ReadinessState;
  detail: string;
}

export interface ReadinessLLM {
  provider: "deterministic" | "ollama";
  model?: string;
  fallbackProvider: "deterministic";
  localOnly: boolean;
}

export interface ReadinessStatus {
  status: "ready" | "degraded";
  checks: Record<string, ReadinessCheck>;
  llm: ReadinessLLM;
}

export type DemoStep = "reset" | "policy" | "memory" | "incident" | "telemetry";

export interface DemoProgress {
  step: DemoStep;
  state: "pending" | "running" | "complete";
}
