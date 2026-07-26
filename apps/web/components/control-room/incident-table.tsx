import { ArrowRight, FileWarning, ShieldCheck } from "lucide-react";
import Link from "next/link";

import type { Incident } from "@/lib/api/types";
import { formatCompactCurrency, formatRelativeTime, humanize } from "@/lib/utils";

import { Badge } from "../ui/badge";
import { buttonStyles } from "../ui/button";
import { Panel } from "../ui/panel";
import { StatePanel } from "../ui/state-panel";

function riskTone(level: Incident["riskLevel"]): "danger" | "warning" | "neutral" {
  if (level === "critical") return "danger";
  if (level === "high" || level === "medium") return "warning";
  return "neutral";
}

export function IncidentTable({ incidents, onRunDemo }: { incidents: Incident[]; onRunDemo: () => void }) {
  return (
    <Panel id="incidents" className="overflow-hidden scroll-mt-8">
      <div className="flex flex-col gap-3 border-b border-white/[0.065] px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-slate-100">Causal incidents</h2>
            <span className="numeric rounded-full bg-white/[0.06] px-2 py-0.5 text-[9px] font-bold text-slate-500">{incidents.length}</span>
          </div>
          <p className="mt-1 text-[11px] text-slate-600">Sensitive actions with memory-attributed policy failures.</p>
        </div>
        <div className="flex items-center gap-2 text-[9px] font-semibold uppercase tracking-[0.12em] text-slate-600">
          <span className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-signal-400" />
          Evidence stream live
        </div>
      </div>

      {incidents.length === 0 ? (
        <StatePanel
          title="No unsafe actions detected"
          description="Run the deterministic refund scenario to create a cross-session incident and trace it back to unsafe memory."
          action={
            <button type="button" onClick={onRunDemo} className={buttonStyles({ variant: "primary", size: "sm" })}>
              Generate demo incident
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          }
        />
      ) : (
        <>
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-white/[0.055] text-[9px] font-bold uppercase tracking-[0.14em] text-slate-600">
                  <th className="px-6 py-3 font-bold">Risk</th>
                  <th className="px-4 py-3 font-bold">Action</th>
                  <th className="px-4 py-3 font-bold">Memory source</th>
                  <th className="px-4 py-3 font-bold">Result</th>
                  <th className="px-4 py-3 font-bold">Detected</th>
                  <th className="px-6 py-3 text-right font-bold"><span className="sr-only">Open incident</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.052]">
                {incidents.map((incident) => (
                  <tr key={incident.id} className="group transition hover:bg-white/[0.025]">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2.5">
                        <div className={`grid h-9 w-9 place-items-center rounded-xl ${incident.riskLevel === "critical" ? "bg-danger-500/10 text-danger-300" : "bg-amber-400/10 text-amber-300"}`}>
                          <span className="numeric text-xs font-bold">{incident.riskScore}</span>
                        </div>
                        <Badge tone={riskTone(incident.riskLevel)}>{incident.riskLevel}</Badge>
                      </div>
                    </td>
                    <td className="px-4 py-4">
                      <div className="text-xs font-semibold text-slate-200">{formatCompactCurrency(incident.action.amount)} refund</div>
                      <div className="mt-1 text-[10px] text-slate-600">{humanize(incident.action.type)}</div>
                    </td>
                    <td className="max-w-[260px] px-4 py-4">
                      <div className="flex items-center gap-2 text-xs text-slate-300">
                        <FileWarning className="h-3.5 w-3.5 shrink-0 text-amber-300" aria-hidden="true" />
                        <span className="truncate">{incident.memory.sourceName}</span>
                      </div>
                      <div className="mt-1 pl-[22px] text-[10px] capitalize text-slate-600">{incident.memory.sourceTrust} source</div>
                    </td>
                    <td className="px-4 py-4">
                      <Badge tone={incident.policyOutcome.toLowerCase().includes("pass") ? "success" : "danger"} dot>
                        {humanize(incident.policyOutcome)}
                      </Badge>
                    </td>
                    <td className="whitespace-nowrap px-4 py-4 text-[11px] text-slate-500">{formatRelativeTime(incident.detectedAt)}</td>
                    <td className="px-6 py-4 text-right">
                      <Link
                        href={`/incidents/${encodeURIComponent(incident.id)}`}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-white/[0.07] text-slate-500 transition hover:border-signal-400/30 hover:bg-signal-400/10 hover:text-signal-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-400/60"
                        aria-label={`Investigate ${incident.title}`}
                      >
                        <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="divide-y divide-white/[0.06] md:hidden">
            {incidents.map((incident) => (
              <Link key={incident.id} href={`/incidents/${encodeURIComponent(incident.id)}`} className="block p-5 transition hover:bg-white/[0.025]">
                <div className="flex items-start justify-between gap-3">
                  <Badge tone={riskTone(incident.riskLevel)}>{incident.riskLevel} · {incident.riskScore}</Badge>
                  <span className="text-[10px] text-slate-600">{formatRelativeTime(incident.detectedAt)}</span>
                </div>
                <div className="mt-3 text-sm font-semibold text-slate-200">{formatCompactCurrency(incident.action.amount)} refund</div>
                <div className="mt-2 flex items-center gap-2 text-[11px] text-slate-500">
                  <FileWarning className="h-3.5 w-3.5 text-amber-300" />
                  <span className="truncate">{incident.memory.sourceName}</span>
                  <ArrowRight className="ml-auto h-3.5 w-3.5" />
                </div>
              </Link>
            ))}
          </div>
        </>
      )}

      {incidents.length > 0 ? (
        <div className="flex items-center gap-2 border-t border-white/[0.055] bg-white/[0.018] px-5 py-3 text-[10px] text-slate-600 sm:px-6">
          <ShieldCheck className="h-3.5 w-3.5 text-signal-400/70" aria-hidden="true" />
          Risk is scored with a transparent policy heuristic — no model-generated severity.
        </div>
      ) : null}
    </Panel>
  );
}
