import { CheckCheck, CircleAlert, Database, ShieldAlert } from "lucide-react";

import type { Incident } from "@/lib/api/types";

const metricDefinitions = [
  {
    key: "open",
    label: "Open incidents",
    detail: "Awaiting remediation",
    icon: CircleAlert,
    tone: "text-danger-300 bg-danger-500/10 border-danger-400/20",
  },
  {
    key: "critical",
    label: "Critical memories",
    detail: "Unsafe active context",
    icon: Database,
    tone: "text-amber-300 bg-amber-400/10 border-amber-400/20",
  },
  {
    key: "violations",
    label: "Policy violations",
    detail: "Business-level failures",
    icon: ShieldAlert,
    tone: "text-danger-300 bg-danger-500/10 border-danger-400/20",
  },
  {
    key: "replays",
    label: "Replays completed",
    detail: "Repairs verified",
    icon: CheckCheck,
    tone: "text-signal-300 bg-signal-400/10 border-signal-400/20",
  },
] as const;

export function MetricStrip({ incidents }: { incidents: Incident[] }) {
  const values: Record<(typeof metricDefinitions)[number]["key"], number> = {
    open: incidents.filter((incident) => ["open", "investigating"].includes(incident.status)).length,
    critical: new Set(
      incidents
        .filter(
          (incident) => incident.riskLevel === "critical" && incident.memory.status.toLowerCase() === "active",
        )
        .map((incident) => incident.memory.id),
    ).size,
    violations: incidents.filter((incident) => incident.policyOutcome.toLowerCase().includes("violation")).length,
    replays: incidents.filter((incident) => ["remediated", "closed"].includes(incident.status)).length,
  };

  return (
    <div className="grid overflow-hidden rounded-2xl border border-white/[0.075] bg-ink-900/75 shadow-panel sm:grid-cols-2 xl:grid-cols-4">
      {metricDefinitions.map(({ key, label, detail, icon: Icon, tone }, index) => (
        <div
          key={key}
          className={`flex min-h-[124px] items-center gap-4 p-5 sm:p-6 ${index > 0 ? "border-t border-white/[0.065] sm:border-l" : ""} ${index === 2 ? "sm:border-l-0 xl:border-l" : ""} ${index > 1 ? "sm:border-t xl:border-t-0" : ""}`}
        >
          <div className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl border ${tone}`}>
            <Icon className="h-[18px] w-[18px]" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <div className="numeric text-2xl font-semibold tracking-[-0.04em] text-white">{values[key]}</div>
            <div className="mt-0.5 text-xs font-semibold text-slate-300">{label}</div>
            <div className="mt-1 text-[10px] text-slate-600">{detail}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
