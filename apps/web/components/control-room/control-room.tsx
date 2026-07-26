"use client";

import { ArrowRight, Braces, Play, Radio, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";

import { api } from "@/lib/api/client";
import type { DemoProgress as DemoProgressState } from "@/lib/api/types";
import { useAsyncResource } from "@/lib/hooks/use-async-resource";

import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Panel } from "../ui/panel";
import { Skeleton } from "../ui/skeleton";
import { StatePanel } from "../ui/state-panel";
import { DemoProgress } from "./demo-progress";
import { IncidentTable } from "./incident-table";
import { LifecycleRail } from "./lifecycle-rail";
import { MetricStrip } from "./metric-strip";

const initialProgress: DemoProgressState[] = ["reset", "policy", "memory", "incident", "telemetry"].map((step) => ({
  step: step as DemoProgressState["step"],
  state: "pending",
}));

export function ControlRoom() {
  const router = useRouter();
  const loadIncidents = useCallback(() => api.listIncidents(), []);
  const { data: incidents, error, loading, refresh } = useAsyncResource(loadIncidents);
  const [runningDemo, setRunningDemo] = useState(false);
  const [demoProgress, setDemoProgress] = useState<DemoProgressState[]>(initialProgress);
  const [demoError, setDemoError] = useState<string | null>(null);

  const runDemo = useCallback(async () => {
    if (runningDemo) return;
    setRunningDemo(true);
    setDemoError(null);
    setDemoProgress(initialProgress);
    try {
      const incidentId = await api.runDemoScenario(setDemoProgress);
      router.push(`/incidents/${encodeURIComponent(incidentId)}`);
    } catch (caught) {
      setDemoError(caught instanceof Error ? caught.message : "The scenario could not be completed.");
      setRunningDemo(false);
      void refresh();
    }
  }, [refresh, router, runningDemo]);

  return (
    <div className="space-y-7">
      <section className="relative overflow-hidden rounded-[24px] border border-white/[0.08] bg-[linear-gradient(105deg,rgba(17,23,34,.96),rgba(13,17,25,.88))] px-5 py-7 shadow-glow sm:px-8 sm:py-9 xl:px-10">
        <div className="pointer-events-none absolute -right-16 -top-24 h-72 w-72 rounded-full border border-signal-400/[0.08]" />
        <div className="pointer-events-none absolute -right-2 -top-10 h-44 w-44 rounded-full border border-signal-400/[0.08]" />
        <div className="relative grid gap-8 xl:grid-cols-[1fr_420px] xl:items-end">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="success" dot>System observing</Badge>
              <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-600">support-refund-agent</span>
            </div>
            <h1 className="mt-5 max-w-3xl text-balance text-[clamp(2rem,4vw,3.55rem)] font-semibold leading-[1.03] tracking-[-0.052em] text-white">
              Find the memory behind the decision.
            </h1>
            <p className="mt-4 max-w-2xl text-sm leading-6 text-slate-400 sm:text-[15px] sm:leading-7">
              RecallRoot reconstructs cross-session causal chains from SigNoz telemetry, then lets you quarantine unsafe context and prove the repair with a replay.
            </p>
          </div>
          <div className="flex flex-col gap-3 xl:items-end">
            <Button variant="primary" size="lg" onClick={() => void runDemo()} loading={runningDemo} className="w-full sm:w-auto">
              {!runningDemo ? <Play className="h-4 w-4 fill-current" aria-hidden="true" /> : null}
              {runningDemo ? "Generating incident…" : "Run demo scenario"}
              {!runningDemo ? <ArrowRight className="h-4 w-4" aria-hidden="true" /> : null}
            </Button>
            <p className="max-w-sm text-center text-[10px] leading-4 text-slate-600 xl:text-right">
              Resets local demo data, runs Session A + B, and emits linked OpenTelemetry traces.
            </p>
          </div>
        </div>
      </section>

      <LifecycleRail />

      {loading && !incidents ? (
        <div className="grid overflow-hidden rounded-2xl border border-white/[0.075] bg-ink-900/75 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="flex min-h-[124px] items-center gap-4 border-white/[0.06] p-6 sm:border-l first:border-l-0">
              <Skeleton className="h-10 w-10" />
              <div className="space-y-2"><Skeleton className="h-6 w-12" /><Skeleton className="h-3 w-28" /><Skeleton className="h-2 w-20" /></div>
            </div>
          ))}
        </div>
      ) : error && !incidents ? (
        <Panel>
          <StatePanel title="Control room unavailable" description={error.message} kind="error" onRetry={() => void refresh()} compact />
        </Panel>
      ) : (
        <MetricStrip incidents={incidents ?? []} />
      )}

      <div className="grid gap-5 2xl:grid-cols-[minmax(0,1fr)_330px]">
        {error && incidents ? (
          <Panel><StatePanel title="Incident refresh failed" description={error.message} kind="error" onRetry={() => void refresh()} compact /></Panel>
        ) : loading && !incidents ? (
          <Panel className="min-h-[360px] p-6"><Skeleton className="h-8 w-48" /><div className="mt-8 space-y-4">{Array.from({ length: 3 }).map((_, index) => <Skeleton key={index} className="h-14 w-full" />)}</div></Panel>
        ) : (
          <IncidentTable incidents={incidents ?? []} onRunDemo={() => void runDemo()} />
        )}

        <aside className="space-y-5">
          <Panel className="overflow-hidden">
            <div className="border-b border-white/[0.06] px-5 py-4">
              <div className="flex items-center gap-2 text-xs font-semibold text-slate-200">
                <Radio className="h-3.5 w-3.5 text-signal-400" aria-hidden="true" />
                Why ordinary monitoring misses it
              </div>
            </div>
            <div className="space-y-4 p-5">
              <div className="flex items-center justify-between gap-4 rounded-xl border border-signal-400/15 bg-signal-400/[0.055] px-3.5 py-3">
                <div><div className="text-[10px] font-semibold text-slate-300">Tool call</div><div className="mt-1 text-[9px] text-slate-600">issue_refund</div></div>
                <Badge tone="success">200 OK</Badge>
              </div>
              <div className="flex justify-center"><div className="h-5 w-px bg-gradient-to-b from-signal-400/25 to-danger-400/30" /></div>
              <div className="flex items-center justify-between gap-4 rounded-xl border border-danger-400/20 bg-danger-500/[0.065] px-3.5 py-3">
                <div><div className="text-[10px] font-semibold text-slate-300">Business outcome</div><div className="mt-1 text-[9px] text-slate-600">Approval skipped</div></div>
                <Badge tone="danger">Violation</Badge>
              </div>
              <p className="text-[10px] leading-4 text-slate-600">Healthy infrastructure can still produce unsafe agent behavior. RecallRoot evaluates policy outcomes independently.</p>
            </div>
          </Panel>

          <Panel className="p-5">
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-200"><Braces className="h-3.5 w-3.5 text-sky-300" /> Transparent risk model</div>
            <div className="mt-4 space-y-2 text-[10px]">
              <div className="flex justify-between text-slate-500"><span>Untrusted source</span><span className="numeric text-slate-300">+35</span></div>
              <div className="flex justify-between text-slate-500"><span>Stale policy</span><span className="numeric text-slate-300">+20</span></div>
              <div className="flex justify-between text-slate-500"><span>Sensitive action</span><span className="numeric text-slate-300">+20</span></div>
              <div className="flex justify-between text-slate-500"><span>Approval missing</span><span className="numeric text-slate-300">+15</span></div>
              <div className="my-3 h-px bg-white/[0.07]" />
              <div className="flex items-center justify-between"><span className="font-semibold text-slate-300">Critical</span><span className="numeric text-base font-bold text-danger-300">90</span></div>
            </div>
          </Panel>

          <div className="flex items-start gap-3 px-2 text-[10px] leading-4 text-slate-700">
            <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-signal-400/60" />
            Built for one story, end to end: explain a harmful memory, remove it, replay the request, and verify the safer outcome.
          </div>
        </aside>
      </div>

      {runningDemo || demoError ? (
        <DemoProgress steps={demoProgress} error={demoError ?? undefined} onDismiss={demoError ? () => setDemoError(null) : undefined} />
      ) : null}
    </div>
  );
}
