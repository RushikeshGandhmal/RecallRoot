import type {
  CausalGraph,
  CausalGraphEdge,
  CausalGraphNode,
  CausalNodeKind,
  CausalMemoryRemediation,
  ComparisonSide,
  GraphEvidence,
  GraphLog,
  HealthStatus,
  Incident,
  IncidentStatus,
  Investigation,
  OperativeReplayMemory,
  ReadinessCheck,
  ReadinessState,
  ReadinessStatus,
  ReplayComparison,
  RiskFactor,
  RiskLevel,
} from "./types";

export function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function arrayOf(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function text(value: unknown, fallback = ""): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function number(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

function boolean(value: unknown, fallback = false): boolean {
  if (typeof value === "boolean") return value;
  if (value === "true" || value === 1) return true;
  if (value === "false" || value === 0) return false;
  return fallback;
}

function requiredRecord(value: unknown, label: string): Record<string, unknown> {
  const record = asRecord(value);
  if (Object.keys(record).length === 0) {
    throw new TypeError(`${label} is missing from the API response.`);
  }
  return record;
}

function requiredText(
  record: Record<string, unknown>,
  keys: string[],
  label: string,
): string {
  const value = firstText(record, keys).trim();
  if (!value) throw new TypeError(`${label} is missing from the API response.`);
  return value;
}

function requiredNumber(
  record: Record<string, unknown>,
  keys: string[],
  label: string,
): number {
  for (const key of keys) {
    const value = record[key];
    if (value !== undefined && value !== null && value !== "") {
      const parsed = number(value, Number.NaN);
      if (Number.isFinite(parsed)) return parsed;
    }
  }
  throw new TypeError(`${label} is missing from the API response.`);
}

function firstText(record: Record<string, unknown>, keys: string[], fallback = ""): string {
  for (const key of keys) {
    const value = text(record[key]);
    if (value) return value;
  }
  return fallback;
}

function firstNumber(record: Record<string, unknown>, keys: string[], fallback = 0): number {
  for (const key of keys) {
    const value = record[key];
    if (value !== undefined && value !== null && value !== "") return number(value, fallback);
  }
  return fallback;
}

export function titleCase(value: string): string {
  return value
    .replace(/[._-]+/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function normalizeEvidenceSource(value: unknown, fallback: string): string {
  const source = text(value).trim() || fallback;
  switch (source.toLowerCase().replace(/[ .-]+/g, "_")) {
    case "signoz_mcp":
      return "SigNoz MCP";
    case "signoz":
    case "signoz_telemetry":
      return "SigNoz";
    case "local":
    case "local_evidence":
    case "local_otel_evidence":
      return "Local evidence";
    default:
      return titleCase(source);
  }
}

function normalizeWarnings(...values: unknown[]): string[] {
  const warnings = values.flatMap((value) =>
    Array.isArray(value) ? value : typeof value === "string" ? [value] : [],
  );
  return Array.from(
    new Set(warnings.map((warning) => text(warning).trim()).filter(Boolean)),
  );
}

export function normalizeRiskLevel(value: unknown, score: number): RiskLevel {
  const explicit = text(value).toLowerCase();
  if (["low", "medium", "high", "critical"].includes(explicit)) {
    return explicit as RiskLevel;
  }
  if (score >= 80) return "critical";
  if (score >= 60) return "high";
  if (score >= 30) return "medium";
  return "low";
}

function normalizeIncidentStatus(value: unknown): IncidentStatus {
  const status = text(value, "open").toLowerCase();
  if (["open", "investigating", "remediated", "closed"].includes(status)) {
    return status as IncidentStatus;
  }
  if (["resolved", "replayed"].includes(status)) return "remediated";
  return "open";
}

function normalizeRiskFactors(value: unknown): RiskFactor[] {
  if (Array.isArray(value)) {
    return value.map((item) => {
      if (typeof item === "string") return { label: item, points: 0 };
      const record = asRecord(item);
      return {
        label: firstText(record, ["label", "reason", "name", "factor"], "Risk factor"),
        points: firstNumber(record, ["points", "score", "value"]),
        detail: firstText(record, ["detail", "description", "reason"]) || undefined,
      };
    });
  }
  const record = asRecord(value);
  return Object.entries(record).map(([label, points]) => ({ label: titleCase(label), points: number(points) }));
}

export function normalizeIncident(value: unknown): Incident {
  const record = requiredRecord(value, "Incident");
  const action = requiredRecord(record.action ?? record.sensitive_action, "Incident action");
  const actionResult = asRecord(action.result);
  const decision = asRecord(actionResult.decision);
  const memory = requiredRecord(
    record.memory ?? record.influencing_memory,
    "Influencing memory",
  );
  const risk = asRecord(record.risk ?? record.risk_explanation);
  const riskScore = firstNumber(record, ["risk_score", "riskScore"], firstNumber(risk, ["score", "total"]));
  const amount = firstNumber(action, ["amount", "refund_amount"], firstNumber(record, ["amount"]));
  const id = requiredText(record, ["incident_id", "id"], "Incident ID");
  const policyOutcome =
    firstText(record, ["policy_outcome", "outcome"]) ||
    requiredText(action, ["policy_outcome"], "Policy outcome");
  const rawTitle = firstText(record, ["title", "name"]);

  return {
    id,
    title: rawTitle || (amount > 0 ? `Policy violation: ${formatCurrency(amount)} refund` : "Policy violation detected"),
    status: normalizeIncidentStatus(record.status),
    riskScore,
    riskLevel: normalizeRiskLevel(record.risk_level ?? risk.level, riskScore),
    riskFactors: normalizeRiskFactors(record.risk_factors ?? risk.factors ?? risk.breakdown),
    policyOutcome,
    summary: firstText(record, ["summary", "description", "explanation"]) || undefined,
    detectedAt: firstText(record, ["detected_at", "created_at", "timestamp"]) || undefined,
    sessionId: firstText(record, ["session_id", "agent_session_id"]) || undefined,
    action: {
      id: firstText(action, ["id", "action_id"]) || undefined,
      type: requiredText(action, ["type", "action_type", "tool"], "Action type"),
      amount,
      customerId: firstText(action, ["customer_id", "customerId"]) || undefined,
      sensitivity: firstText(action, ["sensitivity"], "high") || undefined,
      approvalRequired:
        action.approval_required === undefined ? undefined : boolean(action.approval_required),
      approvalPresent:
        action.approval_present === undefined ? undefined : boolean(action.approval_present),
      outcome: firstText(action, ["outcome", "result"]) || undefined,
      traceId: firstText(action, ["trace_id"]) || firstText(record, ["trace_id"]) || undefined,
      spanId: firstText(action, ["span_id"]) || undefined,
      decisionProvider:
        firstText(decision, ["provider", "requested_provider"]) || undefined,
      decisionModel:
        firstText(decision, ["response_model", "model"]) || undefined,
      decisionFallback:
        decision.fallback === undefined ? undefined : boolean(decision.fallback),
      decisionFallbackReason:
        firstText(decision, ["fallback_reason", "fallbackReason"]) || undefined,
    },
    memory: {
      id: requiredText(memory, ["id", "memory_id"], "Memory ID"),
      content: firstText(memory, ["content", "text", "instruction"]) || undefined,
      sourceName: firstText(memory, ["source_name", "source", "filename"], "Unknown source"),
      sourceType: firstText(memory, ["source_type", "type"]) || undefined,
      sourceTrust: firstText(memory, ["source_trust", "trust", "trust_level"], "unknown"),
      status: firstText(memory, ["status"], "active"),
      createdAt: firstText(memory, ["created_at", "written_at"]) || undefined,
      retrievalCount:
        memory.retrieval_count === undefined ? undefined : number(memory.retrieval_count),
      originTraceId: firstText(memory, ["created_trace_id", "origin_trace_id", "trace_id"]) || undefined,
      originSpanId: firstText(memory, ["created_span_id", "origin_span_id", "span_id"]) || undefined,
    },
  };
}

export function normalizeIncidentList(payload: unknown): Incident[] {
  if (Array.isArray(payload)) return payload.map(normalizeIncident);
  const record = asRecord(payload);
  const items = record.incidents ?? record.items ?? record.results ?? record.data;
  return arrayOf(items).map(normalizeIncident);
}

function normalizeNodeKind(value: unknown): CausalNodeKind {
  const kind = text(value).toLowerCase().replace(/[.-]/g, "_");
  if (["source", "external_source", "document", "source_ingestion", "ingest_source"].includes(kind)) return "source";
  if (["memory_write", "write", "memory_creation", "memory_written"].includes(kind)) return "memory_write";
  if (["memory", "memory_record", "stored_memory"].includes(kind)) return "memory";
  if (["memory_use", "memory_read", "retrieval", "memory_retrieval"].includes(kind)) return "memory_use";
  if (["decision", "agent_decision", "policy_decision"].includes(kind)) return "decision";
  if (["action", "tool", "tool_action", "execute_tool"].includes(kind)) return "action";
  if (["outcome", "evaluation", "policy_outcome", "violation"].includes(kind)) return "outcome";
  return "unknown";
}

function inferSession(kind: CausalNodeKind): string {
  if (["source", "memory_write", "memory"].includes(kind)) return "Session A";
  return "Session B";
}

function normalizeLogs(value: unknown): GraphLog[] {
  return arrayOf(value).map((item) => {
    if (typeof item === "string") return { body: item };
    const record = asRecord(item);
    return {
      timestamp: firstText(record, ["timestamp", "time", "observed_at"]) || undefined,
      severity: firstText(record, ["severity", "level"]) || undefined,
      body: firstText(record, ["body", "message", "event"], "Telemetry event"),
      attributes: Object.keys(asRecord(record.attributes)).length ? asRecord(record.attributes) : undefined,
    };
  });
}

function normalizeGraphNode(value: unknown, index: number): CausalGraphNode {
  const record = asRecord(value);
  const data = asRecord(record.data);
  const merged = { ...record, ...data };
  const firstEvidence = asRecord(arrayOf(record.evidence)[0]);
  const rawKind = merged.kind ?? merged.node_type ?? merged.type ?? merged.span_type ?? merged.name;
  const kind = normalizeNodeKind(rawKind);
  const rawPosition = asRecord(record.position);
  const hasPosition = Number.isFinite(rawPosition.x) && Number.isFinite(rawPosition.y);
  const explicitAttributes = asRecord(merged.attributes ?? merged.span_attributes);
  const attributes = Object.keys(explicitAttributes).length > 0 ? explicitAttributes : data;
  const label = firstText(merged, ["label", "title", "display_name", "name"], titleCase(kind));
  return {
    id: firstText(record, ["id", "node_id", "span_id"], `node-${index + 1}`),
    kind,
    label,
    description: firstText(merged, ["description", "subtitle", "detail", "content", "sanitized_preview"]) || undefined,
    session: firstText(merged, ["session", "session_label", "session_id"], inferSession(kind)),
    status: firstText(merged, ["status", "outcome", "trust", "source_trust", "policy_outcome"]) || undefined,
    timestamp: firstText(merged, ["timestamp", "start_time", "created_at"]) || undefined,
    traceId: firstText(merged, ["trace_id", "traceId"], firstText(firstEvidence, ["trace_id"])) || undefined,
    spanId: firstText(merged, ["span_id", "spanId"], firstText(firstEvidence, ["span_id"])) || undefined,
    evidenceUrl: firstText(merged, ["signoz_url", "evidence_url", "url"], firstText(firstEvidence, ["url"])) || undefined,
    attributes,
    logs: normalizeLogs(merged.logs ?? merged.events),
    position: hasPosition ? { x: number(rawPosition.x), y: number(rawPosition.y) } : undefined,
  };
}

function normalizeEdgeKind(value: unknown): CausalGraphEdge["kind"] {
  const kind = text(value).toLowerCase().replace(/[.-]/g, "_");
  if (kind.includes("cross") || kind.includes("link")) return "cross_trace";
  if (kind.includes("parent") || kind.includes("child")) return "parent_child";
  return "causal";
}

function normalizeGraphEdge(value: unknown, index: number): CausalGraphEdge {
  const record = asRecord(value);
  const source = firstText(record, ["source", "source_id", "from"]);
  const target = firstText(record, ["target", "target_id", "to"]);
  const kind = normalizeEdgeKind(record.kind ?? record.type ?? record.edge_type);
  return {
    id: firstText(record, ["id", "edge_id"], `${source || "source"}-${target || "target"}-${index}`),
    source,
    target,
    label: firstText(record, ["label", "relationship"]) || (kind === "cross_trace" ? "OTel span link" : undefined),
    kind,
  };
}

function normalizeEvidence(value: unknown, index: number): GraphEvidence {
  if (typeof value === "string") {
    return { id: `evidence-${index}`, title: "Telemetry evidence", detail: value };
  }
  const record = asRecord(value);
  const rawKind = firstText(record, ["kind", "type", "source"]);
  return {
    id: firstText(record, ["id", "evidence_id"], `evidence-${index}`),
    nodeId: firstText(record, ["node_id", "nodeId"]) || undefined,
    title: firstText(record, ["title", "label", "name"], "Telemetry evidence"),
    detail: firstText(record, ["detail", "description", "summary", "body", "span_name"], "Evidence captured in trace"),
    kind: rawKind ? normalizeEvidenceSource(rawKind, rawKind) : undefined,
    timestamp: firstText(record, ["timestamp", "created_at"]) || undefined,
    traceId: firstText(record, ["trace_id"]) || undefined,
    spanId: firstText(record, ["span_id"]) || undefined,
    signozUrl: firstText(record, ["signoz_url", "url", "evidence_url"]) || undefined,
    attributes: Object.keys(asRecord(record.attributes)).length ? asRecord(record.attributes) : undefined,
  };
}

export function normalizeGraph(payload: unknown): CausalGraph {
  const record = requiredRecord(payload, "Causal graph");
  const graph = Object.keys(asRecord(record.graph)).length ? asRecord(record.graph) : record;
  const rawNodes = arrayOf(graph.nodes);
  if (rawNodes.length === 0) {
    throw new TypeError("Causal graph nodes are missing from the API response.");
  }
  const nodes = rawNodes.map(normalizeGraphNode);
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges = arrayOf(graph.edges)
    .map(normalizeGraphEdge)
    .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target));
  const evidenceById = new Map<string, GraphEvidence>();
  rawNodes.forEach((rawNode, nodeIndex) => {
    const nodeRecord = asRecord(rawNode);
    arrayOf(nodeRecord.evidence).forEach((item, evidenceIndex) => {
      const normalized = normalizeEvidence(item, evidenceIndex);
      evidenceById.set(normalized.id, { ...normalized, nodeId: nodes[nodeIndex]?.id });
    });
  });
  const graphEvidence = arrayOf(graph.evidence);
  const outerEvidence = graph === record ? [] : arrayOf(record.evidence);
  [...graphEvidence, ...outerEvidence].forEach((item, evidenceIndex) => {
    const normalized = normalizeEvidence(item, evidenceIndex);
    const existing = evidenceById.get(normalized.id);
    evidenceById.set(normalized.id, existing ? { ...normalized, nodeId: existing.nodeId } : normalized);
  });
  const rawSource =
    firstText(graph, ["source", "evidence_source"]) ||
    firstText(record, ["source", "evidence_source"]);
  if (!rawSource) {
    throw new TypeError("Causal graph evidence source is missing from the API response.");
  }
  const source = normalizeEvidenceSource(rawSource, "Unknown evidence");
  return {
    nodes,
    edges,
    evidence: Array.from(evidenceById.values()),
    source,
    warnings: normalizeWarnings(graph.warnings, record.warnings),
    generatedAt:
      firstText(
        graph,
        ["generated_at", "created_at"],
        firstText(record, ["generated_at", "created_at"]),
      ) || undefined,
  };
}

export function normalizeInvestigation(payload: unknown): Investigation {
  const record = requiredRecord(payload, "Investigation");
  const investigation = Object.keys(asRecord(record.investigation)).length > 0
    ? asRecord(record.investigation)
    : record;
  const summary = requiredText(
    investigation,
    ["summary", "explanation", "answer", "root_cause"],
    "Investigation summary",
  );
  const rawSource =
    firstText(investigation, ["source", "provider"]) ||
    firstText(record, ["source", "provider"]);
  if (!rawSource) {
    throw new TypeError("Investigation evidence source is missing from the API response.");
  }
  const findingsValue = investigation.findings ?? investigation.facts ?? investigation.steps ?? investigation.key_findings;
  const findings = arrayOf(findingsValue).map((item) => {
    if (typeof item === "string") return item;
    const finding = asRecord(item);
    return firstText(finding, ["detail", "summary", "description", "title"], "Evidence finding");
  });
  const rawEvidence = [
    ...arrayOf(investigation.evidence),
    ...(investigation === record ? [] : arrayOf(record.evidence)),
  ];
  const evidence = new Map<string, GraphEvidence>();
  rawEvidence.forEach((item, index) => {
    const normalized = normalizeEvidence(item, index);
    evidence.set(normalized.id, normalized);
  });
  return {
    summary,
    explanation:
      firstText(investigation, ["explanation", "answer", "root_cause"]) || undefined,
    findings,
    evidence: Array.from(evidence.values()),
    source: normalizeEvidenceSource(rawSource, "Unknown evidence"),
    warnings: normalizeWarnings(investigation.warnings, record.warnings),
    investigatedAt: firstText(investigation, ["investigated_at", "created_at"]) || undefined,
  };
}

function normalizeComparisonSide(
  value: unknown,
  label: string,
): ComparisonSide {
  const record = requiredRecord(value, `${label} comparison`);
  const memory = asRecord(record.memory);
  const action = asRecord(record.action);
  const memoryStatus =
    firstText(memory, ["status"]) ||
    requiredText(record, ["memory_status"], `${label} memory status`);
  const memoryTrust =
    firstText(memory, ["source_trust", "trust"]) ||
    requiredText(record, ["memory_trust", "source_trust"], `${label} memory trust`);
  const tool =
    firstText(action, ["type", "action_type", "tool"]) ||
    requiredText(record, ["tool", "action_type"], `${label} tool`);
  const policyOutcome =
    firstText(action, ["policy_outcome"]) ||
    requiredText(record, ["policy_outcome", "outcome"], `${label} policy outcome`);
  return {
    label,
    memoryId: firstText(memory, ["id", "memory_id"], firstText(record, ["memory_id"])) || undefined,
    memoryStatus,
    memoryTrust,
    memoryContent:
      firstText(memory, ["content", "instruction"]) ||
      firstText(record, ["memory_content"]) ||
      undefined,
    decision: requiredText(record, ["decision", "agent_decision"], `${label} decision`),
    tool,
    policyOutcome,
    riskScore: requiredNumber(record, ["risk_score", "risk"], `${label} risk score`),
    traceId:
      firstText(record, ["trace_id"]) ||
      requiredText(action, ["trace_id"], `${label} trace ID`),
    createdAt: firstText(record, ["created_at", "completed_at"]) || undefined,
  };
}

function normalizeCausalMemory(
  value: unknown,
  original: ComparisonSide,
  memoryQuarantined: boolean,
): CausalMemoryRemediation {
  const record = asRecord(value);
  return {
    id: firstText(record, ["id", "memory_id"], original.memoryId ?? "") || undefined,
    sourceTrust: firstText(record, ["source_trust", "trust"], original.memoryTrust),
    beforeStatus: firstText(record, ["before_status", "original_status"], original.memoryStatus),
    afterStatus: firstText(
      record,
      ["after_status", "remediated_status"],
      memoryQuarantined ? "quarantined" : "unknown",
    ),
    remediation: firstText(record, ["remediation", "action"], "quarantine"),
  };
}

function normalizeOperativeReplayMemory(
  value: unknown,
  replay: ComparisonSide,
): OperativeReplayMemory {
  const record = asRecord(value);
  return {
    id: firstText(record, ["id", "memory_id"], replay.memoryId ?? "") || undefined,
    sourceTrust: firstText(record, ["source_trust", "trust"], replay.memoryTrust),
    status: firstText(record, ["status"], replay.memoryStatus),
  };
}

export function normalizeComparison(payload: unknown, incidentId: string): ReplayComparison {
  const record = requiredRecord(payload, "Replay comparison");
  const nestedComparison = asRecord(record.comparison);
  const comparison = Object.keys(nestedComparison).length > 0
    ? { ...record, ...nestedComparison }
    : record;
  const originalRaw = comparison.original ?? comparison.before ?? comparison.original_run;
  const replayRaw = comparison.replay ?? comparison.after ?? comparison.replay_run;
  const original = normalizeComparisonSide(originalRaw, "Before remediation");
  const replay = normalizeComparisonSide(replayRaw, "After remediation");
  const memoryQuarantined = boolean(comparison.memory_quarantined, false);
  const causalMemory = normalizeCausalMemory(
    comparison.causal_memory,
    original,
    memoryQuarantined,
  );
  const operativeReplayMemory = normalizeOperativeReplayMemory(
    comparison.operative_replay_memory,
    replay,
  );
  const result = requiredText(
    comparison,
    ["result", "replay_result", "status"],
    "Replay result",
  );
  const verifiedAt = firstText(comparison, ["verified_at"]);
  const verified =
    boolean(comparison.verified, false) ||
    (result.toLowerCase() === "improved" && Boolean(verifiedAt));
  return {
    incidentId: firstText(comparison, ["incident_id"], incidentId),
    replayId: firstText(comparison, ["replay_id", "id"]) || undefined,
    result,
    verified,
    original,
    replay,
    causalMemory,
    operativeReplayMemory,
    explanation: firstText(comparison, ["explanation", "summary", "diff_summary"]) || undefined,
    verifiedAt: verifiedAt || undefined,
    createdAt: firstText(comparison, ["created_at", "completed_at"]) || undefined,
  };
}

export function normalizeHealth(payload: unknown): HealthStatus {
  const record = asRecord(payload);
  return {
    status: firstText(record, ["status"], "unknown"),
    service: firstText(record, ["service", "name"]) || undefined,
    telemetry: firstText(record, ["telemetry", "telemetry_export", "signoz", "observability"]) || undefined,
  };
}

export function normalizeReadiness(payload: unknown): ReadinessStatus {
  const record = requiredRecord(payload, "Readiness");
  const rawStatus = requiredText(record, ["status"], "Readiness status").toLowerCase();
  if (rawStatus !== "ready" && rawStatus !== "degraded") {
    throw new TypeError(`Unsupported readiness status: ${rawStatus}`);
  }
  const rawChecks = requiredRecord(record.checks, "Readiness checks");
  const checks: Record<string, ReadinessCheck> = {};
  for (const [name, value] of Object.entries(rawChecks)) {
    const check = requiredRecord(value, `Readiness check ${name}`);
    const status = requiredText(check, ["status"], `${name} readiness status`).toLowerCase();
    if (!["ready", "degraded", "unconfigured", "unavailable"].includes(status)) {
      throw new TypeError(`Unsupported ${name} readiness status: ${status}`);
    }
    checks[name] = {
      status: status as ReadinessState,
      detail: requiredText(check, ["detail"], `${name} readiness detail`),
    };
  }
  const rawLlm = requiredRecord(record.llm, "Decision provider readiness");
  const provider = requiredText(rawLlm, ["provider"], "Decision provider").toLowerCase();
  if (provider !== "deterministic" && provider !== "ollama") {
    throw new TypeError(`Unsupported decision provider: ${provider}`);
  }
  const fallbackProvider = requiredText(
    rawLlm,
    ["fallback_provider", "fallbackProvider"],
    "Fallback decision provider",
  ).toLowerCase();
  if (fallbackProvider !== "deterministic") {
    throw new TypeError(`Unsupported fallback decision provider: ${fallbackProvider}`);
  }
  const localOnlyValue = rawLlm.local_only ?? rawLlm.localOnly;
  if (typeof localOnlyValue !== "boolean") {
    throw new TypeError("Decision provider local-only status is missing.");
  }
  return {
    status: rawStatus,
    checks,
    llm: {
      provider,
      model: firstText(rawLlm, ["model"]) || undefined,
      fallbackProvider,
      localOnly: localOnlyValue,
    },
  };
}

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(amount);
}
