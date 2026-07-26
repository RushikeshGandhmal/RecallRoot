import {
  BrainCircuit,
  CheckCircle2,
  Database,
  FileInput,
  FileWarning,
  Gavel,
  Search,
  ShieldAlert,
  Wrench,
} from "lucide-react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import type { CausalGraphNode, CausalNodeKind } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export type CausalNodeData = { node: CausalGraphNode } & Record<string, unknown>;
export type CausalFlowNode = Node<CausalNodeData, "causal">;

const kindPresentation: Record<
  CausalNodeKind,
  { icon: typeof Database; eyebrow: string; color: string; iconStyle: string }
> = {
  source: {
    icon: FileWarning,
    eyebrow: "External source",
    color: "border-amber-400/25 shadow-[0_12px_35px_rgba(239,168,63,.06)]",
    iconStyle: "border-amber-400/20 bg-amber-400/10 text-amber-300",
  },
  memory_write: {
    icon: FileInput,
    eyebrow: "Memory write",
    color: "border-violet-400/20 shadow-[0_12px_35px_rgba(139,92,246,.05)]",
    iconStyle: "border-violet-400/20 bg-violet-400/10 text-violet-300",
  },
  memory: {
    icon: Database,
    eyebrow: "Durable memory",
    color: "border-violet-400/20 shadow-[0_12px_35px_rgba(139,92,246,.05)]",
    iconStyle: "border-violet-400/20 bg-violet-400/10 text-violet-300",
  },
  memory_use: {
    icon: Search,
    eyebrow: "Memory retrieval",
    color: "border-sky-400/20 shadow-[0_12px_35px_rgba(56,189,248,.05)]",
    iconStyle: "border-sky-400/20 bg-sky-400/10 text-sky-300",
  },
  decision: {
    icon: BrainCircuit,
    eyebrow: "Agent decision",
    color: "border-sky-400/20 shadow-[0_12px_35px_rgba(56,189,248,.05)]",
    iconStyle: "border-sky-400/20 bg-sky-400/10 text-sky-300",
  },
  action: {
    icon: Wrench,
    eyebrow: "Sensitive action",
    color: "border-danger-400/25 shadow-[0_12px_35px_rgba(244,91,105,.06)]",
    iconStyle: "border-danger-400/20 bg-danger-500/10 text-danger-300",
  },
  outcome: {
    icon: ShieldAlert,
    eyebrow: "Policy outcome",
    color: "border-danger-400/30 shadow-[0_12px_35px_rgba(244,91,105,.08)]",
    iconStyle: "border-danger-400/20 bg-danger-500/10 text-danger-300",
  },
  unknown: {
    icon: Gavel,
    eyebrow: "Telemetry span",
    color: "border-white/10",
    iconStyle: "border-white/10 bg-white/[0.05] text-slate-400",
  },
};

export function CausalNode({ data, selected }: NodeProps<CausalFlowNode>) {
  const presentation = kindPresentation[data.node.kind];
  const Icon = data.node.status?.toLowerCase().includes("pass") ? CheckCircle2 : presentation.icon;
  const untrusted = data.node.status?.toLowerCase().includes("untrusted");

  return (
    <div
      className={cn(
        "relative w-[220px] rounded-2xl border bg-ink-900/95 p-3.5 shadow-lg backdrop-blur-lg transition duration-200",
        presentation.color,
        selected && "-translate-y-0.5 border-signal-400/55 ring-2 ring-signal-400/15",
      )}
    >
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-2 !border-ink-900 !bg-slate-500" />
      <div className="flex items-start gap-3">
        <div className={cn("grid h-8 w-8 shrink-0 place-items-center rounded-lg border", presentation.iconStyle)}>
          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[8px] font-bold uppercase tracking-[0.15em] text-slate-600">{presentation.eyebrow}</div>
          <div className="mt-1 truncate text-[11px] font-semibold text-slate-200">{data.node.label}</div>
        </div>
      </div>
      {data.node.description ? <p className="mt-3 line-clamp-2 min-h-[32px] text-[9px] leading-4 text-slate-500">{data.node.description}</p> : null}
      <div className="mt-3 flex items-center justify-between gap-2 border-t border-white/[0.06] pt-2.5">
        <span className="text-[8px] font-semibold uppercase tracking-[0.1em] text-slate-700">{data.node.session}</span>
        {data.node.status ? (
          <span className={cn("max-w-[90px] truncate rounded-full border px-1.5 py-0.5 text-[7px] font-bold uppercase tracking-[0.08em]", untrusted || data.node.status.toLowerCase().includes("violation") ? "border-danger-400/20 bg-danger-500/10 text-danger-300" : "border-white/[0.08] bg-white/[0.04] text-slate-500")}>
            {data.node.status}
          </span>
        ) : null}
      </div>
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-2 !border-ink-900 !bg-signal-400/80" />
    </div>
  );
}
