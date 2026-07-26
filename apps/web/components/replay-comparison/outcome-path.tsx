import { BrainCircuit, Check, Database, ShieldCheck, Wrench, X } from "lucide-react";

import type { ComparisonSide } from "@/lib/api/types";
import { cn, humanize } from "@/lib/utils";

const steps = [
  { key: "memory", label: "Memory state", icon: Database },
  { key: "decision", label: "Agent decision", icon: BrainCircuit },
  { key: "tool", label: "Selected tool", icon: Wrench },
  { key: "policy", label: "Policy evaluation", icon: ShieldCheck },
] as const;

export function OutcomePath({
  side,
  repaired,
  memoryLabel = "Operative memory",
}: {
  side: ComparisonSide;
  repaired: boolean;
  memoryLabel?: string;
}) {
  const values: Record<(typeof steps)[number]["key"], string> = {
    memory: `${humanize(side.memoryStatus)} · ${humanize(side.memoryTrust)}`,
    decision: humanize(side.decision),
    tool: humanize(side.tool),
    policy: humanize(side.policyOutcome),
  };
  return (
    <ol className="relative space-y-2.5">
      {steps.map(({ key, label, icon: Icon }, index) => (
        <li key={key} className="relative flex gap-3">
          {index < steps.length - 1 ? <div className="absolute left-[15px] top-8 h-[calc(100%+10px)] w-px bg-white/[0.07]" /> : null}
          <div className={cn("relative z-10 grid h-8 w-8 shrink-0 place-items-center rounded-lg border", repaired ? "border-signal-400/20 bg-signal-400/[0.08] text-signal-300" : "border-danger-400/20 bg-danger-500/[0.08] text-danger-300")}>
            <Icon className="h-3.5 w-3.5" />
          </div>
          <div className="min-w-0 flex-1 rounded-xl border border-white/[0.055] bg-black/10 px-3 py-2.5">
            <div className="text-[8px] font-bold uppercase tracking-[0.12em] text-slate-700">{key === "memory" ? memoryLabel : label}</div>
            <div className="mt-1.5 flex items-center justify-between gap-3 text-[10px] font-semibold text-slate-300">
              <span className="truncate">{values[key]}</span>
              {key === "policy" ? repaired ? <Check className="h-3.5 w-3.5 shrink-0 text-signal-300" /> : <X className="h-3.5 w-3.5 shrink-0 text-danger-300" /> : null}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}
