import type {
  CausalGraph,
  CausalGraphNode,
  GraphEvidence,
  Investigation,
} from "./types";

function spanKey(item: Pick<GraphEvidence, "traceId" | "spanId">): string | undefined {
  return item.traceId && item.spanId ? `${item.traceId}:${item.spanId}` : undefined;
}

function nodeSpanKey(node: CausalGraphNode): string | undefined {
  return node.traceId && node.spanId ? `${node.traceId}:${node.spanId}` : undefined;
}

/**
 * Prefer investigation evidence for the same span while retaining the graph node
 * association. This makes MCP-returned links visible without duplicating the
 * equivalent graph evidence card.
 */
export function mergeInvestigationEvidence(
  graph: CausalGraph,
  investigation: Investigation | null,
): GraphEvidence[] {
  const nodeBySpan = new Map<string, string>();
  graph.nodes.forEach((node) => {
    const key = nodeSpanKey(node);
    if (key) nodeBySpan.set(key, node.id);
  });

  const evidenceByKey = new Map<string, GraphEvidence>();
  const order: string[] = [];
  const add = (item: GraphEvidence) => {
    const key = spanKey(item) ?? item.id;
    const existing = evidenceByKey.get(key);
    const nodeId = item.nodeId ?? existing?.nodeId ?? nodeBySpan.get(spanKey(item) ?? "");
    if (!existing) order.push(key);
    evidenceByKey.set(key, { ...existing, ...item, nodeId });
  };

  graph.evidence.forEach(add);
  investigation?.evidence.forEach(add);
  return order.flatMap((key) => {
    const item = evidenceByKey.get(key);
    return item ? [item] : [];
  });
}
