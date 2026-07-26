import { Binoculars, CheckCircle2, Microscope, Play, ShieldOff, Waypoints } from "lucide-react";

const stages = [
  { label: "Observe", detail: "Detect unsafe outcome", icon: Binoculars },
  { label: "Trace origin", detail: "Cross-session provenance", icon: Waypoints },
  { label: "Explain", detail: "Evidence-backed cause", icon: Microscope },
  { label: "Quarantine", detail: "Disable bad memory", icon: ShieldOff },
  { label: "Replay", detail: "Repeat exact request", icon: Play },
  { label: "Verify", detail: "Compare repaired trace", icon: CheckCircle2 },
];

export function LifecycleRail() {
  return (
    <section aria-labelledby="workflow-title">
      <div className="mb-3 flex items-center gap-3">
        <h2 id="workflow-title" className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500">
          Operator workflow
        </h2>
        <div className="h-px flex-1 bg-white/[0.06]" />
        <span className="text-[10px] text-slate-600">Closed-loop remediation</span>
      </div>
      <ol className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6">
        {stages.map(({ label, detail, icon: Icon }, index) => (
          <li key={label} className="group relative min-h-[88px] rounded-xl border border-white/[0.065] bg-white/[0.025] p-3.5 transition hover:border-white/[0.11] hover:bg-white/[0.04]">
            <div className="flex items-start justify-between gap-3">
              <div className="grid h-7 w-7 place-items-center rounded-lg bg-white/[0.045] text-slate-400 transition group-hover:text-signal-300">
                <Icon className="h-3.5 w-3.5" aria-hidden="true" />
              </div>
              <span className="numeric text-[9px] font-bold text-slate-700">0{index + 1}</span>
            </div>
            <div className="mt-3 text-[11px] font-semibold text-slate-300">{label}</div>
            <div className="mt-1 text-[9px] text-slate-600">{detail}</div>
          </li>
        ))}
      </ol>
    </section>
  );
}
