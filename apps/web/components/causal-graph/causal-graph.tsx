"use client";

import { GitBranch, Radio, Route, TriangleAlert } from "lucide-react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
  type NodeTypes,
} from "@xyflow/react";
import { useMemo } from "react";

import type { CausalGraph as CausalGraphModel, CausalGraphNode, CausalNodeKind } from "@/lib/api/types";

import { Badge } from "../ui/badge";
import { EvidenceSourceBadge } from "../ui/evidence-source-badge";
import { Panel } from "../ui/panel";
import { StatePanel } from "../ui/state-panel";
import { CausalNode, type CausalFlowNode } from "./causal-node";

const nodeTypes: NodeTypes = { causal: CausalNode };

const kindOrder: Record<CausalNodeKind, number> = {
  source: 0,
  memory_write: 1,
  memory: 2,
  memory_use: 3,
  decision: 4,
  action: 5,
  outcome: 6,
  unknown: 7,
};

function nodePosition(node: CausalGraphNode, index: number): { x: number; y: number } {
  if (node.position) return node.position;
  const order = kindOrder[node.kind] ?? index;
  if (order <= 2) return { x: order * 285, y: 58 };
  if (order <= 6) return { x: (order - 3) * 285, y: 310 };
  return { x: index * 260, y: 560 };
}

function edgeColor(kind: string): string {
  if (kind === "cross_trace") return "#7EF2BC";
  if (kind === "parent_child") return "#64748B";
  return "#64748B";
}

function minimapColor(node: Node): string {
  const causalNode = node as CausalFlowNode;
  switch (causalNode.data.node.kind) {
    case "source": return "#EFA83F";
    case "action":
    case "outcome": return "#F45B69";
    case "memory":
    case "memory_write": return "#A78BFA";
    default: return "#38BDF8";
  }
}

function GraphHeader({ graph }: { graph: CausalGraphModel }) {
  return (
    <div className="flex flex-col gap-3 border-b border-white/[0.065] px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between sm:px-5">
      <div className="flex items-center gap-3">
        <div className="grid h-8 w-8 place-items-center rounded-lg border border-signal-400/15 bg-signal-400/[0.07] text-signal-300">
          <GitBranch className="h-3.5 w-3.5" aria-hidden="true" />
        </div>
        <div>
          <h2 className="text-xs font-semibold text-slate-200">Cross-session causal graph</h2>
          <p className="mt-0.5 text-[9px] text-slate-600">Select a node to inspect its telemetry evidence.</p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <EvidenceSourceBadge source={graph.source} />
        <Badge tone="success" dot>{graph.nodes.length} causal nodes</Badge>
      </div>
    </div>
  );
}

function GraphWarnings({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) return null;
  return (
    <div className="flex items-start gap-2.5 border-b border-amber-400/15 bg-amber-400/[0.045] px-5 py-3 text-amber-200/80" role="status">
      <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-300" />
      <div className="min-w-0">
        <div className="text-[9px] font-bold uppercase tracking-[0.11em] text-amber-300">Evidence source notice</div>
        <ul className="mt-1 space-y-1 text-[9px] leading-4 text-slate-500">
          {warnings.map((warning) => <li key={warning}>{warning}</li>)}
        </ul>
      </div>
    </div>
  );
}

export function CausalGraph({
  graph,
  selectedId,
  onSelect,
}: {
  graph: CausalGraphModel;
  selectedId?: string;
  onSelect: (node: CausalGraphNode) => void;
}) {
  const nodes = useMemo<CausalFlowNode[]>(
    () =>
      graph.nodes.map((node, index) => ({
        id: node.id,
        type: "causal",
        position: nodePosition(node, index),
        data: { node },
        selected: node.id === selectedId,
        draggable: true,
      })),
    [graph.nodes, selectedId],
  );
  const edges = useMemo<Edge[]>(
    () =>
      graph.edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: edge.label,
        type: edge.kind === "cross_trace" ? "default" : "smoothstep",
        animated: edge.kind === "cross_trace",
        markerEnd: { type: MarkerType.ArrowClosed, color: edgeColor(edge.kind), width: 14, height: 14 },
        style: {
          stroke: edgeColor(edge.kind),
          strokeWidth: edge.kind === "cross_trace" ? 2 : 1.25,
          strokeDasharray: edge.kind === "cross_trace" ? "6 5" : undefined,
          opacity: edge.kind === "cross_trace" ? 0.9 : 0.5,
        },
        labelStyle: { fill: "#94A3B8", fontSize: 8, fontWeight: 600 },
        labelBgStyle: { fill: "#0D1119", fillOpacity: 0.94 },
        labelBgPadding: [5, 3] as [number, number],
        labelBgBorderRadius: 6,
      })),
    [graph.edges],
  );

  if (graph.nodes.length === 0) {
    return (
      <Panel className="overflow-hidden">
        <GraphHeader graph={graph} />
        <GraphWarnings warnings={graph.warnings} />
        <StatePanel title="No causal evidence found" description="SigNoz returned no causal telemetry for this incident. Verify ingestion, then rebuild the graph." compact />
      </Panel>
    );
  }

  return (
    <Panel className="overflow-hidden">
      <GraphHeader graph={graph} />
      <GraphWarnings warnings={graph.warnings} />

      <div className="relative h-[520px] w-full bg-[radial-gradient(circle_at_45%_0%,rgba(126,242,188,.04),transparent_32%)] sm:h-[590px] xl:h-[640px]">
        <div className="pointer-events-none absolute left-4 top-4 z-10 flex flex-wrap gap-2">
          <div className="flex items-center gap-2 rounded-lg border border-violet-400/10 bg-ink-950/75 px-2.5 py-1.5 text-[8px] font-bold uppercase tracking-[0.13em] text-violet-300/70 backdrop-blur">
            <Radio className="h-2.5 w-2.5" /> Session A · origin trace
          </div>
          <div className="flex items-center gap-2 rounded-lg border border-sky-400/10 bg-ink-950/75 px-2.5 py-1.5 text-[8px] font-bold uppercase tracking-[0.13em] text-sky-300/70 backdrop-blur">
            <Route className="h-2.5 w-2.5" /> Session B · action trace
          </div>
        </div>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodeClick={(_, node) => onSelect((node as CausalFlowNode).data.node)}
          onPaneClick={() => undefined}
          fitView
          fitViewOptions={{ padding: 0.16, maxZoom: 1 }}
          minZoom={0.22}
          maxZoom={1.7}
          proOptions={{ hideAttribution: true }}
          colorMode="dark"
          aria-label="Cross-session causal graph"
        >
          <Background color="rgba(148,163,184,.13)" gap={24} size={1} variant={BackgroundVariant.Dots} />
          <Controls position="bottom-left" showInteractive={false} />
          <MiniMap
            position="bottom-right"
            pannable
            zoomable
            nodeColor={minimapColor}
            nodeStrokeWidth={2}
            maskColor="rgba(8,10,15,.72)"
            className="!h-20 !w-28 sm:!h-24 sm:!w-36"
          />
        </ReactFlow>
      </div>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-white/[0.055] bg-white/[0.015] px-5 py-3 text-[8px] font-semibold uppercase tracking-[0.1em] text-slate-700">
        <span className="flex items-center gap-2"><span className="h-px w-5 bg-slate-500" /> Parent–child</span>
        <span className="flex items-center gap-2"><span className="w-5 border-t border-dashed border-signal-400" /> Cross-trace OTel link</span>
        <span className="ml-auto normal-case tracking-normal text-slate-700">Drag to rearrange · Scroll to zoom</span>
      </div>
    </Panel>
  );
}
