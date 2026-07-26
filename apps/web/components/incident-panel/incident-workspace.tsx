"use client";

import {
  AlertTriangle,
  ArrowLeft,
  ChevronRight,
  CircleAlert,
  ExternalLink,
  FileWarning,
  Fingerprint,
  ShieldAlert,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { CausalGraph } from "@/components/causal-graph/causal-graph";
import { api } from "@/lib/api/client";
import type { CausalGraphNode, Investigation } from "@/lib/api/types";
import { useAsyncResource } from "@/lib/hooks/use-async-resource";
import {
  buildSignozTraceUrl,
  formatCurrency,
  formatDateTime,
  humanize,
  truncateIdentifier,
} from "@/lib/utils";

import { Badge } from "../ui/badge";
import { buttonStyles } from "../ui/button";
import {
  isLocalEvidenceSource,
  isMcpEvidenceSource,
} from "../ui/evidence-source-badge";
import { Panel } from "../ui/panel";
import { Skeleton } from "../ui/skeleton";
import { StatePanel } from "../ui/state-panel";
import { EvidencePanel } from "./evidence-panel";
import {
  EvidenceSyncStatus,
  type EvidenceSyncState,
} from "./evidence-sync-status";
import { RemediationBar } from "./remediation-bar";
import { RiskBreakdown } from "./risk-breakdown";

type ActiveAction = "investigating" | "quarantining" | "replaying" | null;

export function IncidentWorkspace({ incidentId }: { incidentId: string }) {
  const router = useRouter();
  const loadIncident = useCallback(() => api.getIncident(incidentId), [incidentId]);
  const loadGraph = useCallback(() => api.getGraph(incidentId), [incidentId]);
  const {
    data: incident,
    error: incidentError,
    loading: incidentLoading,
    refresh: refreshIncident,
    setData: setIncident,
  } = useAsyncResource(loadIncident);
  const {
    data: graph,
    error: graphError,
    loading: graphLoading,
    refresh: refreshGraph,
    setData: setGraph,
  } = useAsyncResource(loadGraph);
  const [selectedNode, setSelectedNode] = useState<CausalGraphNode | null>(null);
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [activeAction, setActiveAction] = useState<ActiveAction>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [evidenceSync, setEvidenceSync] = useState<EvidenceSyncState>("idle");
  const evidenceSyncRun = useRef(0);

  const syncEvidence = useCallback(async () => {
    if (evidenceSync === "syncing") return;
    const run = ++evidenceSyncRun.current;
    setEvidenceSync("syncing");
    try {
      const result = await api.waitForSignozGraph(incidentId, graph ?? undefined);
      if (run !== evidenceSyncRun.current) return;
      setGraph(result);
      setEvidenceSync(isLocalEvidenceSource(result.source) ? "degraded" : "live");
    } catch {
      if (run === evidenceSyncRun.current) setEvidenceSync("degraded");
    }
  }, [evidenceSync, graph, incidentId, setGraph]);

  useEffect(() => {
    if (!graph) return;
    if (!isLocalEvidenceSource(graph.source)) return;
    if (evidenceSync !== "idle") return;
    const timeout = window.setTimeout(() => void syncEvidence(), 0);
    return () => window.clearTimeout(timeout);
  }, [evidenceSync, graph, syncEvidence]);

  useEffect(
    () => () => {
      evidenceSyncRun.current += 1;
    },
    [],
  );

  const runAction = useCallback(
    async (kind: Exclude<ActiveAction, null>, operation: () => Promise<void>) => {
      if (activeAction) return;
      setActiveAction(kind);
      setActionError(null);
      try {
        await operation();
      } catch (caught) {
        setActionError(caught instanceof Error ? caught.message : "The remediation action failed.");
      } finally {
        setActiveAction(null);
      }
    },
    [activeAction],
  );

  const investigate = () =>
    runAction("investigating", async () => {
      const result = await api.investigate(incidentId);
      setInvestigation(result);
      setIncident((current) => (current ? { ...current, status: "investigating" } : current));
    });

  const quarantine = () =>
    runAction("quarantining", async () => {
      if (!incident) return;
      await api.quarantineMemory(incident.memory.id);
      setIncident((current) =>
        current
          ? { ...current, status: "investigating", memory: { ...current.memory, status: "quarantined" } }
          : current,
      );
      await Promise.allSettled([refreshIncident(), refreshGraph()]);
    });

  const replay = () =>
    runAction("replaying", async () => {
      await api.replayIncident(incidentId);
      router.push(`/incidents/${encodeURIComponent(incidentId)}/comparison`);
    });

  if (incidentLoading && !incident) return <IncidentWorkspaceSkeleton />;

  if (incidentError && !incident) {
    return (
      <div className="space-y-5">
        <Link href="/" className={buttonStyles({ variant: "ghost", size: "sm", className: "-ml-3" })}><ArrowLeft className="h-3.5 w-3.5" /> Control room</Link>
        <Panel><StatePanel title="Incident unavailable" description={incidentError.message} kind="error" onRetry={() => void refreshIncident()} /></Panel>
      </div>
    );
  }

  if (!incident) return null;
  const quarantined = incident.memory.status.toLowerCase() === "quarantined";
  const actionTraceUrl = buildSignozTraceUrl(incident.action.traceId);
  const effectiveSelectedNode = graph
    ? graph.nodes.find((node) => node.id === selectedNode?.id) ??
      graph.nodes.find((node) => node.kind === "outcome") ??
      graph.nodes[0] ??
      null
    : null;

  return (
    <div className="space-y-5">
      <nav className="flex flex-wrap items-center gap-1.5 text-[10px] text-slate-600" aria-label="Breadcrumb">
        <Link href="/" className="rounded-md transition hover:text-slate-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-400/60">Control room</Link>
        <ChevronRight className="h-3 w-3 text-slate-800" />
        <span>Incidents</span>
        <ChevronRight className="h-3 w-3 text-slate-800" />
        <span className="font-mono text-slate-400">{incident.id}</span>
      </nav>

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_410px]">
        <Panel className="relative overflow-hidden p-5 sm:p-7">
          <div className="pointer-events-none absolute -right-20 -top-24 h-56 w-56 rounded-full bg-danger-500/[0.055] blur-3xl" />
          <div className="relative">
            <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="danger" dot>{incident.policyOutcome}</Badge>
                  <Badge tone={quarantined ? "success" : "neutral"}>{quarantined ? "Memory quarantined" : incident.status}</Badge>
                  {incident.action.decisionProvider ? (
                    <Badge
                      tone={incident.action.decisionFallback ? "warning" : "info"}
                      title={
                        incident.action.decisionFallback
                          ? `The requested model path failed safely (${humanize(incident.action.decisionFallbackReason ?? "provider error")}); the deterministic provider completed the decision.`
                          : "Decision provider recorded on the action trace."
                      }
                    >
                      {incident.action.decisionFallback ? (
                        <>
                          Deterministic fallback ·{" "}
                          {incident.action.decisionModel ?? "requested model"} ·{" "}
                          {humanize(incident.action.decisionFallbackReason ?? "provider error")}
                        </>
                      ) : (
                        incident.action.decisionModel ??
                        humanize(incident.action.decisionProvider)
                      )}
                    </Badge>
                  ) : null}
                  <span className="text-[9px] font-semibold uppercase tracking-[0.13em] text-slate-700">detected {formatDateTime(incident.detectedAt)}</span>
                </div>
                <h1 className="mt-4 text-balance text-2xl font-semibold tracking-[-0.035em] text-white sm:text-3xl">
                  Policy violation: {formatCurrency(incident.action.amount)} refund
                </h1>
                <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-500">
                  An untrusted memory from an earlier session caused the agent to skip manager approval while every infrastructure signal remained healthy.
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-3 rounded-xl border border-danger-400/15 bg-danger-500/[0.055] px-4 py-3">
                <ShieldAlert className="h-5 w-5 text-danger-300" />
                <div><div className="numeric text-lg font-bold text-danger-300">{incident.riskScore}</div><div className="text-[8px] font-bold uppercase tracking-[0.12em] text-slate-600">{incident.riskLevel} risk</div></div>
              </div>
            </div>
            <div className="mt-6 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-xl border border-white/[0.055] bg-black/10 p-3">
                <div className="flex items-center gap-1.5 text-[8px] font-bold uppercase tracking-[0.12em] text-slate-700"><CircleAlert className="h-3 w-3" /> Action</div>
                <div className="mt-2 truncate text-[10px] font-semibold text-slate-300">{humanize(incident.action.type)}</div>
              </div>
              <div className="rounded-xl border border-white/[0.055] bg-black/10 p-3">
                <div className="flex items-center gap-1.5 text-[8px] font-bold uppercase tracking-[0.12em] text-slate-700"><FileWarning className="h-3 w-3" /> Memory source</div>
                <div className="mt-2 truncate text-[10px] font-semibold text-amber-300">{incident.memory.sourceName}</div>
              </div>
              <div className="rounded-xl border border-white/[0.055] bg-black/10 p-3">
                <div className="flex items-center gap-1.5 text-[8px] font-bold uppercase tracking-[0.12em] text-slate-700"><AlertTriangle className="h-3 w-3" /> Approval</div>
                <div className="mt-2 text-[10px] font-semibold text-danger-300">Required · Missing</div>
              </div>
              <div className="rounded-xl border border-white/[0.055] bg-black/10 p-3">
                <div className="flex items-center gap-1.5 text-[8px] font-bold uppercase tracking-[0.12em] text-slate-700"><Fingerprint className="h-3 w-3" /> Action trace</div>
                {actionTraceUrl ? (
                  <a href={actionTraceUrl} target="_blank" rel="noreferrer" className="mt-2 flex items-center gap-1.5 truncate font-mono text-[9px] text-sky-300 transition hover:text-sky-200">
                    {truncateIdentifier(incident.action.traceId, 6)} <ExternalLink className="h-2.5 w-2.5 shrink-0" />
                  </a>
                ) : <div className="mt-2 text-[9px] text-slate-700">Not recorded</div>}
              </div>
            </div>
          </div>
        </Panel>
        <RiskBreakdown incident={incident} />
      </section>

      <EvidenceSyncStatus
        state={
          graph && !isLocalEvidenceSource(graph.source) ? "live" : evidenceSync
        }
        onRetry={() => void syncEvidence()}
      />

      {actionError ? (
        <div className="flex items-start gap-3 rounded-xl border border-danger-400/20 bg-danger-500/[0.07] px-4 py-3 text-[11px] text-danger-300" role="alert">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span className="flex-1 leading-5">{actionError}</span>
          <button type="button" onClick={() => setActionError(null)} className="rounded p-0.5 hover:bg-danger-500/10" aria-label="Dismiss error"><X className="h-3.5 w-3.5" /></button>
        </div>
      ) : null}

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.6fr)_minmax(330px,.65fr)]">
        {graphLoading && !graph ? (
          <Panel className="h-[640px] p-5"><div className="flex justify-between"><Skeleton className="h-8 w-52" /><Skeleton className="h-6 w-28" /></div><Skeleton className="mt-5 h-[550px] w-full" /></Panel>
        ) : graphError && !graph ? (
          <Panel className="min-h-[520px]"><StatePanel title="Causal graph unavailable" description={graphError.message} kind="error" onRetry={() => void refreshGraph()} /></Panel>
        ) : graph ? (
          <CausalGraph graph={graph} selectedId={effectiveSelectedNode?.id} onSelect={setSelectedNode} />
        ) : null}

        {graph ? (
          <div id="evidence-panel" className="scroll-mt-5"><EvidencePanel graph={graph} selectedNode={effectiveSelectedNode} investigation={investigation} /></div>
        ) : (
          <Panel className="min-h-[520px] p-5"><Skeleton className="h-8 w-44" /><Skeleton className="mt-5 h-28 w-full" /><Skeleton className="mt-4 h-48 w-full" /></Panel>
        )}
      </div>

      <RemediationBar
        incident={incident}
        investigated={
          Boolean(investigation) &&
          !isLocalEvidenceSource(investigation?.source ?? "local_evidence")
        }
        investigationSource={investigation?.source}
        mcpVerified={isMcpEvidenceSource(investigation?.source ?? "")}
        quarantined={quarantined}
        action={activeAction}
        onInvestigate={() => void investigate()}
        onQuarantine={() => void quarantine()}
        onReplay={() => void replay()}
      />
    </div>
  );
}

function IncidentWorkspaceSkeleton() {
  return (
    <div className="space-y-5" aria-label="Loading incident">
      <Skeleton className="h-4 w-60" />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_410px]">
        <Panel className="p-7"><Skeleton className="h-5 w-40" /><Skeleton className="mt-5 h-10 w-3/5" /><Skeleton className="mt-4 h-4 w-4/5" /><div className="mt-7 grid grid-cols-4 gap-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-16" />)}</div></Panel>
        <Panel className="p-6"><div className="flex gap-5"><Skeleton className="h-20 w-20 rounded-full" /><div className="flex-1 space-y-3"><Skeleton className="h-3 w-full" /><Skeleton className="h-3 w-full" /><Skeleton className="h-3 w-3/4" /></div></div></Panel>
      </div>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.6fr)_minmax(330px,.65fr)]"><Skeleton className="h-[640px] rounded-2xl" /><Skeleton className="h-[640px] rounded-2xl" /></div>
    </div>
  );
}
