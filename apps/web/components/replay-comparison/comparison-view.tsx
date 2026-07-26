"use client";

import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  ExternalLink,
  Fingerprint,
  Gauge,
  GitCompareArrows,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useCallback } from "react";

import { api } from "@/lib/api/client";
import type { ComparisonSide } from "@/lib/api/types";
import { useAsyncResource } from "@/lib/hooks/use-async-resource";
import {
  buildSignozTraceUrl,
  cn,
  formatDateTime,
  humanize,
  truncateIdentifier,
} from "@/lib/utils";

import { Badge } from "../ui/badge";
import { buttonStyles } from "../ui/button";
import { Panel } from "../ui/panel";
import { Skeleton } from "../ui/skeleton";
import { StatePanel } from "../ui/state-panel";
import { OutcomePath } from "./outcome-path";

function TraceLink({ side, repaired }: { side: ComparisonSide; repaired: boolean }) {
  const url = buildSignozTraceUrl(side.traceId);
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-white/[0.055] bg-black/10 px-3.5 py-3">
      <div className="min-w-0">
        <div className="flex items-center gap-1.5 text-[8px] font-bold uppercase tracking-[0.12em] text-slate-700"><Fingerprint className="h-2.5 w-2.5" /> Trace ID</div>
        <div className="mt-1.5 truncate font-mono text-[9px] text-slate-400">{truncateIdentifier(side.traceId, 8)}</div>
      </div>
      {url ? (
        <a href={url} target="_blank" rel="noreferrer" className={cn("grid h-8 w-8 shrink-0 place-items-center rounded-lg border transition", repaired ? "border-signal-400/20 bg-signal-400/[0.07] text-signal-300 hover:bg-signal-400/[0.13]" : "border-white/[0.08] bg-white/[0.035] text-slate-500 hover:text-slate-200")} aria-label={`Open ${side.label} trace in SigNoz`}>
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      ) : null}
    </div>
  );
}

function SidePanel({ side, repaired }: { side: ComparisonSide; repaired: boolean }) {
  return (
    <Panel className={cn("relative overflow-hidden", repaired ? "border-signal-400/20 shadow-glow" : "border-danger-400/16")}>
      <div className={cn("absolute inset-x-0 top-0 h-px", repaired ? "bg-gradient-to-r from-transparent via-signal-400/80 to-transparent" : "bg-gradient-to-r from-transparent via-danger-400/60 to-transparent")} />
      <div className="border-b border-white/[0.06] p-5 sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className={cn("text-[9px] font-bold uppercase tracking-[0.16em]", repaired ? "text-signal-300" : "text-danger-300")}>{side.label}</div>
            <h2 className="mt-2 text-xl font-semibold tracking-[-0.025em] text-white">{repaired ? "Approval requested" : "Refund auto-issued"}</h2>
            <p className="mt-2 text-[10px] leading-4 text-slate-600">{repaired ? "Trusted policy memory selected; unsafe causal memory excluded" : "Untrusted causal memory used as operative policy"}</p>
          </div>
          <div className={cn("grid h-11 w-11 shrink-0 place-items-center rounded-xl border", repaired ? "border-signal-400/20 bg-signal-400/[0.08] text-signal-300" : "border-danger-400/20 bg-danger-500/[0.08] text-danger-300")}>
            {repaired ? <CheckCircle2 className="h-5 w-5" /> : <Gauge className="h-5 w-5" />}
          </div>
        </div>
        <div className="mt-5 flex items-end justify-between gap-4 rounded-xl border border-white/[0.055] bg-black/10 p-4">
          <div><div className="text-[8px] font-bold uppercase tracking-[0.13em] text-slate-700">Risk score</div><div className={cn("numeric mt-1 text-3xl font-semibold tracking-[-0.04em]", repaired ? "text-signal-300" : "text-danger-300")}>{side.riskScore}</div></div>
          <Badge tone={repaired ? "success" : "danger"} dot>{side.policyOutcome}</Badge>
        </div>
      </div>
      <div className="p-5 sm:p-6">
        <OutcomePath side={side} repaired={repaired} memoryLabel={repaired ? "Operative replay memory" : "Operative memory"} />
        {side.memoryContent ? (
          <div className={cn("mt-5 rounded-xl border px-4 py-3", repaired ? "border-signal-400/15 bg-signal-400/[0.035]" : "border-danger-400/15 bg-danger-500/[0.035]")}>
            <div className="text-[8px] font-bold uppercase tracking-[0.11em] text-slate-700">{repaired ? "Operative trusted context" : "Operative untrusted context"}</div>
            <blockquote className="mt-1.5 text-[9px] italic leading-4 text-slate-400">“{side.memoryContent}”</blockquote>
          </div>
        ) : null}
        <div className="mt-5"><TraceLink side={side} repaired={repaired} /></div>
      </div>
    </Panel>
  );
}

export function ComparisonView({ incidentId }: { incidentId: string }) {
  const loadComparison = useCallback(() => api.getComparison(incidentId), [incidentId]);
  const { data: comparison, error, loading, refresh } = useAsyncResource(loadComparison);

  if (loading && !comparison) return <ComparisonSkeleton />;
  if (error && !comparison) {
    return (
      <div className="space-y-5">
        <Link href={`/incidents/${encodeURIComponent(incidentId)}`} className={buttonStyles({ variant: "ghost", size: "sm", className: "-ml-3" })}><ArrowLeft className="h-3.5 w-3.5" /> Incident</Link>
        <Panel><StatePanel title="Replay comparison unavailable" description={error.message} kind="error" onRetry={() => void refresh()} action={<Link href={`/incidents/${encodeURIComponent(incidentId)}`} className={buttonStyles({ size: "sm" })}>Return to remediation</Link>} /></Panel>
      </div>
    );
  }
  if (!comparison) return null;

  const riskReduction = Math.max(0, comparison.original.riskScore - comparison.replay.riskScore);
  const rows = [
    {
      label: "Causal memory",
      before: `${humanize(comparison.causalMemory.beforeStatus)} · ${humanize(comparison.causalMemory.sourceTrust)}`,
      after: `${humanize(comparison.causalMemory.afterStatus)} · ${humanize(comparison.causalMemory.remediation)}`,
    },
    {
      label: "Operative memory",
      before: `${humanize(comparison.original.memoryStatus)} · ${humanize(comparison.original.memoryTrust)}`,
      after: `${humanize(comparison.operativeReplayMemory.status)} · ${humanize(comparison.operativeReplayMemory.sourceTrust)}`,
    },
    { label: "Decision", before: humanize(comparison.original.decision), after: humanize(comparison.replay.decision) },
    { label: "Tool", before: humanize(comparison.original.tool), after: humanize(comparison.replay.tool) },
    { label: "Policy", before: humanize(comparison.original.policyOutcome), after: humanize(comparison.replay.policyOutcome) },
    { label: "Risk", before: String(comparison.original.riskScore), after: String(comparison.replay.riskScore) },
  ];

  return (
    <div className="space-y-6">
      <nav className="flex flex-wrap items-center gap-1.5 text-[10px] text-slate-600" aria-label="Breadcrumb">
        <Link href="/" className="transition hover:text-slate-300">Control room</Link><span>/</span>
        <Link href={`/incidents/${encodeURIComponent(incidentId)}`} className="transition hover:text-slate-300">{incidentId}</Link><span>/</span>
        <span className="text-slate-400">Replay comparison</span>
      </nav>

      <section className="relative overflow-hidden rounded-[24px] border border-signal-400/20 bg-[linear-gradient(110deg,rgba(20,45,38,.52),rgba(13,17,25,.94)_65%)] px-5 py-7 shadow-glow sm:px-8 sm:py-9">
        <div className="pointer-events-none absolute -right-16 -top-20 h-64 w-64 rounded-full border border-signal-400/[0.09]" />
        <div className="pointer-events-none absolute right-8 top-6 h-24 w-24 rounded-full bg-signal-400/[0.04] blur-2xl" />
        <div className="relative flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <Badge tone={comparison.verified ? "success" : "warning"} dot>{comparison.verified ? "Repair verified" : humanize(comparison.result)}</Badge>
            <h1 className="mt-5 text-balance text-3xl font-semibold tracking-[-0.045em] text-white sm:text-4xl">Same request. Safer decision.</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">The unsafe causal memory was quarantined, so the replay selected trusted active policy memory. The same request now stops at manager approval and passes the refund policy.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <div className="rounded-xl border border-white/[0.07] bg-black/10 px-4 py-3"><div className="text-[8px] font-bold uppercase tracking-[0.12em] text-slate-700">Risk reduced</div><div className="numeric mt-1 text-xl font-semibold text-signal-300">−{riskReduction}</div></div>
            <div className="rounded-xl border border-white/[0.07] bg-black/10 px-4 py-3"><div className="text-[8px] font-bold uppercase tracking-[0.12em] text-slate-700">Policy</div><div className="mt-1 text-sm font-semibold text-signal-300">Pass</div></div>
          </div>
        </div>
      </section>

      <div className="relative grid gap-5 lg:grid-cols-2">
        <SidePanel side={comparison.original} repaired={false} />
        <div className="pointer-events-none absolute left-1/2 top-24 z-10 hidden h-10 w-10 -translate-x-1/2 place-items-center rounded-full border border-white/[0.1] bg-ink-900 text-slate-500 shadow-xl lg:grid"><ArrowRight className="h-4 w-4" /></div>
        <SidePanel side={comparison.replay} repaired />
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <Panel className="overflow-hidden">
          <div className="flex items-center justify-between gap-4 border-b border-white/[0.06] px-5 py-4 sm:px-6">
            <div><h2 className="text-xs font-semibold text-slate-200">Behavioral diff</h2><p className="mt-1 text-[9px] text-slate-600">Causal remediation and operative replay selection are reported separately.</p></div>
            <GitCompareArrows className="h-4 w-4 text-signal-300" />
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-left">
              <thead><tr className="border-b border-white/[0.055] text-[8px] font-bold uppercase tracking-[0.13em] text-slate-700"><th className="px-6 py-3">Signal</th><th className="px-4 py-3 text-danger-300/70">Before</th><th className="w-10 px-2 py-3" /><th className="px-4 py-3 text-signal-300/70">After</th></tr></thead>
              <tbody className="divide-y divide-white/[0.05]">
                {rows.map((row) => (
                  <tr key={row.label} className="text-[10px]"><th className="px-6 py-3.5 font-semibold text-slate-500">{row.label}</th><td className="px-4 py-3.5 text-slate-400">{row.before}</td><td className="px-2 py-3.5 text-slate-700"><ArrowRight className="h-3 w-3" /></td><td className="px-4 py-3.5 font-semibold text-signal-300">{row.after}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel className="p-5 sm:p-6">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-200"><ShieldCheck className="h-4 w-4 text-signal-300" /> Replay integrity</div>
          <ul className="mt-5 space-y-3">
            {["Exact original customer request", "Same ₹35,000 refund amount", "Same trusted system policy", "Unsafe causal memory is quarantined", "Trusted active memory is operative in replay", "Independent evaluator returns pass"].map((item) => (
              <li key={item} className="flex items-start gap-2.5 text-[10px] leading-4 text-slate-500"><span className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full bg-signal-400/10 text-signal-300"><Check className="h-2.5 w-2.5" /></span>{item}</li>
            ))}
          </ul>
          {comparison.explanation ? <p className="mt-5 rounded-xl border border-white/[0.055] bg-black/10 p-3 text-[9px] leading-4 text-slate-500">{comparison.explanation}</p> : null}
          <div className="mt-5 flex items-center gap-2 text-[8px] font-bold uppercase tracking-[0.12em] text-slate-700"><Sparkles className="h-3 w-3 text-signal-400/60" /> Verified {formatDateTime(comparison.verifiedAt ?? comparison.createdAt)}</div>
        </Panel>
      </div>

      <div className="flex flex-col gap-3 rounded-2xl border border-white/[0.07] bg-white/[0.025] p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
        <div><div className="text-xs font-semibold text-slate-300">Causal loop closed</div><p className="mt-1 text-[10px] text-slate-600">The incident remains available as evidence; the unsafe memory stays quarantined.</p></div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Link href={`/incidents/${encodeURIComponent(incidentId)}`} className={buttonStyles()}><ArrowLeft className="h-3.5 w-3.5" /> Back to evidence</Link>
          <Link href="/" className={buttonStyles({ variant: "primary" })}>Return to control room <ArrowRight className="h-3.5 w-3.5" /></Link>
        </div>
      </div>
    </div>
  );
}

function ComparisonSkeleton() {
  return (
    <div className="space-y-6" aria-label="Loading replay comparison">
      <Skeleton className="h-4 w-64" />
      <Skeleton className="h-56 rounded-[24px]" />
      <div className="grid gap-5 lg:grid-cols-2">{Array.from({ length: 2 }).map((_, index) => <Panel key={index} className="p-6"><Skeleton className="h-7 w-48" /><Skeleton className="mt-6 h-24" /><div className="mt-6 space-y-3">{Array.from({ length: 4 }).map((__, row) => <Skeleton key={row} className="h-14" />)}</div></Panel>)}</div>
    </div>
  );
}
