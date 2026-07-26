import { Info } from "lucide-react";

import type { Incident, RiskFactor } from "@/lib/api/types";
import { cn } from "@/lib/utils";

import { Panel } from "../ui/panel";

const defaultFactors: RiskFactor[] = [
  { label: "Untrusted source", points: 35 },
  { label: "Stale policy", points: 20 },
  { label: "Sensitive refund action", points: 20 },
  { label: "Required approval missing", points: 15 },
];

export function RiskBreakdown({ incident }: { incident: Incident }) {
  const factors = incident.riskFactors.length > 0 ? incident.riskFactors : defaultFactors;
  const angle = Math.max(0, Math.min(100, incident.riskScore)) * 3.6;
  return (
    <Panel className="flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:p-6 xl:flex-col xl:items-stretch 2xl:flex-row 2xl:items-center">
      <div className="flex items-center gap-4 sm:min-w-[190px]">
        <div
          className="relative grid h-[78px] w-[78px] shrink-0 place-items-center rounded-full"
          style={{ background: `conic-gradient(#F45B69 ${angle}deg, rgba(255,255,255,.06) ${angle}deg)` }}
          aria-label={`Risk score ${incident.riskScore} out of 100`}
        >
          <div className="absolute inset-[6px] rounded-full bg-ink-900" />
          <div className="relative text-center"><div className="numeric text-xl font-bold text-white">{incident.riskScore}</div><div className="text-[7px] font-bold uppercase tracking-[0.12em] text-slate-600">of 100</div></div>
        </div>
        <div>
          <div className="text-[9px] font-bold uppercase tracking-[0.13em] text-slate-600">Risk score</div>
          <div className="mt-1 text-lg font-semibold capitalize text-danger-300">{incident.riskLevel}</div>
          <div className="mt-1 flex items-center gap-1 text-[8px] text-slate-700"><Info className="h-2.5 w-2.5" /> Deterministic</div>
        </div>
      </div>
      <div className="h-px bg-white/[0.06] sm:h-20 sm:w-px xl:h-px xl:w-full 2xl:h-20 2xl:w-px" />
      <div className="min-w-0 flex-1 space-y-2">
        {factors.map((factor, index) => (
          <div key={`${factor.label}-${index}`} className="flex items-center justify-between gap-5 text-[10px]">
            <span className="truncate text-slate-500">{factor.label}</span>
            <span className={cn("numeric font-semibold", factor.points > 0 ? "text-danger-300" : "text-slate-500")}>
              {factor.points > 0 ? "+" : ""}{factor.points}
            </span>
          </div>
        ))}
      </div>
    </Panel>
  );
}
