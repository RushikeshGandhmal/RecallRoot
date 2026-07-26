import { Check, Circle, LoaderCircle, X } from "lucide-react";

import type { DemoProgress as DemoProgressState } from "@/lib/api/types";
import { cn, humanize } from "@/lib/utils";

const labels: Record<DemoProgressState["step"], string> = {
  reset: "Reset local scenario",
  policy: "Seed trusted policy",
  memory: "Ingest unsafe memory",
  incident: "Execute ₹35k refund",
  telemetry: "Verify evidence in SigNoz",
};

export function DemoProgress({
  steps,
  error,
  onDismiss,
}: {
  steps: DemoProgressState[];
  error?: string;
  onDismiss?: () => void;
}) {
  return (
    <div className="fixed bottom-4 right-4 z-50 w-[calc(100vw-2rem)] max-w-sm animate-fade-up overflow-hidden rounded-2xl border border-white/[0.1] bg-ink-900/95 shadow-[0_28px_90px_rgba(0,0,0,.5)] backdrop-blur-2xl sm:bottom-6 sm:right-6" role="status" aria-live="polite">
      <div className="relative overflow-hidden border-b border-white/[0.07] px-5 py-4">
        {!error && steps.some((step) => step.state === "running") ? <div className="absolute inset-x-0 top-0 h-px overflow-hidden bg-signal-400/15"><div className="h-full w-1/3 animate-scan bg-signal-400" /></div> : null}
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-xs font-semibold text-slate-100">{error ? "Scenario stopped" : "Building causal incident"}</div>
            <div className="mt-1 text-[10px] text-slate-600">Deterministic refund-agent workflow</div>
          </div>
          {onDismiss ? (
            <button type="button" onClick={onDismiss} className="rounded-lg p-1 text-slate-600 hover:bg-white/[0.05] hover:text-slate-300" aria-label="Dismiss">
              <X className="h-3.5 w-3.5" />
            </button>
          ) : null}
        </div>
      </div>
      <ol className="space-y-3 p-5">
        {steps.map((step) => (
          <li key={step.step} className="flex items-center gap-3">
            <div
              className={cn(
                "grid h-6 w-6 place-items-center rounded-full border",
                step.state === "complete" && "border-signal-400/30 bg-signal-400/10 text-signal-300",
                step.state === "running" && "border-sky-400/30 bg-sky-400/10 text-sky-300",
                step.state === "pending" && "border-white/[0.08] bg-white/[0.025] text-slate-700",
              )}
            >
              {step.state === "complete" ? <Check className="h-3 w-3" /> : step.state === "running" ? <LoaderCircle className="h-3 w-3 animate-spin" /> : <Circle className="h-2.5 w-2.5" />}
            </div>
            <div className="min-w-0 flex-1">
              <div className={cn("text-[11px] font-medium", step.state === "pending" ? "text-slate-600" : "text-slate-300")}>{labels[step.step]}</div>
              {step.state === "running" ? <div className="mt-0.5 text-[9px] text-sky-400/70">Emitting {humanize(step.step)} telemetry…</div> : null}
            </div>
          </li>
        ))}
      </ol>
      {error ? <div className="border-t border-danger-400/15 bg-danger-500/[0.06] px-5 py-3 text-[10px] leading-4 text-danger-300">{error}</div> : null}
    </div>
  );
}
