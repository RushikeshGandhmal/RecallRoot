"use client";

import {
  Check,
  Clock3,
  Copy,
  ExternalLink,
  FileSearch,
  Fingerprint,
  ListTree,
  ScrollText,
  Sparkles,
} from "lucide-react";
import { useMemo, useState } from "react";

import { mergeInvestigationEvidence } from "@/lib/api/evidence";
import type { CausalGraph, CausalGraphNode, Investigation } from "@/lib/api/types";
import {
  buildSignozTraceUrl,
  cn,
  formatDateTime,
  stringifyAttribute,
  truncateIdentifier,
} from "@/lib/utils";

import { Badge } from "../ui/badge";
import { buttonStyles } from "../ui/button";
import { EvidenceSourceBadge, isLocalEvidenceSource } from "../ui/evidence-source-badge";
import { Panel } from "../ui/panel";
import { StatePanel } from "../ui/state-panel";
import { TraceEvidenceCard } from "./trace-evidence-card";

type EvidenceTab = "evidence" | "attributes" | "logs";

function CopyIdentifier({ value, label }: { value?: string; label: string }) {
  const [copied, setCopied] = useState(false);
  if (!value) return <span className="text-slate-700">Not recorded</span>;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1_600);
    } catch {
      setCopied(false);
    }
  };
  return (
    <button
      type="button"
      onClick={() => void copy()}
      className="group inline-flex max-w-full items-center gap-1.5 rounded-md font-mono text-[9px] text-slate-400 transition hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-400/60"
      aria-label={`Copy ${label}`}
      title={value}
    >
      <span className="truncate">{truncateIdentifier(value, 7)}</span>
      {copied ? <Check className="h-3 w-3 shrink-0 text-signal-300" /> : <Copy className="h-3 w-3 shrink-0 opacity-0 transition group-hover:opacity-100" />}
    </button>
  );
}

export function EvidencePanel({
  graph,
  selectedNode,
  investigation,
}: {
  graph: CausalGraph;
  selectedNode: CausalGraphNode | null;
  investigation: Investigation | null;
}) {
  const [tab, setTab] = useState<EvidenceTab>("evidence");
  const mergedEvidence = useMemo(
    () => mergeInvestigationEvidence(graph, investigation),
    [graph, investigation],
  );
  const nodeEvidence = useMemo(
    () => mergedEvidence.filter((item) => !item.nodeId || item.nodeId === selectedNode?.id),
    [mergedEvidence, selectedNode?.id],
  );
  const attributes = selectedNode ? Object.entries(selectedNode.attributes) : [];
  const traceUrl = selectedNode?.evidenceUrl ?? buildSignozTraceUrl(selectedNode?.traceId);
  const activeSource = investigation?.source ?? graph.source;
  const localEvidence = isLocalEvidenceSource(activeSource);
  const tabs: Array<{ id: EvidenceTab; label: string; icon: typeof FileSearch; count?: number }> = [
    { id: "evidence", label: "Evidence", icon: FileSearch, count: nodeEvidence.length },
    { id: "attributes", label: "Attributes", icon: ListTree, count: attributes.length },
    { id: "logs", label: "Logs", icon: ScrollText, count: selectedNode?.logs.length ?? 0 },
  ];

  return (
    <Panel className="flex min-h-[520px] flex-col overflow-hidden sm:min-h-[590px] xl:min-h-[640px]">
      <div className="border-b border-white/[0.065] px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-xs font-semibold text-slate-200">Evidence inspector</h2>
            <p className="mt-1 text-[9px] text-slate-600">Trace-backed facts, never inferred graph data.</p>
          </div>
          <EvidenceSourceBadge source={activeSource} />
        </div>
      </div>

      {investigation ? (
        <div className="border-b border-signal-400/15 bg-signal-400/[0.045] px-5 py-4 animate-fade-up">
          <div className="flex items-center gap-2 text-[9px] font-bold uppercase tracking-[0.12em] text-signal-300">
            <Sparkles className="h-3 w-3" /> Investigation complete
          </div>
          <p className="mt-2 text-[11px] leading-[1.65] text-slate-300">
            {investigation.explanation ?? investigation.summary}
          </p>
          {investigation.findings.length > 0 ? (
            <ul className="mt-3 space-y-1.5">
              {investigation.findings.map((finding, index) => (
                <li key={`${finding}-${index}`} className="flex gap-2 text-[10px] leading-4 text-slate-400">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-signal-400/70" />{finding}
                </li>
              ))}
            </ul>
          ) : null}
          {investigation.evidence.length > 0 ? (
            <div className="mt-3">
              <div className="mb-2 flex items-center justify-between gap-3">
                <span className="text-[8px] font-bold uppercase tracking-[0.12em] text-slate-600">Verified trace links</span>
                <span className="numeric text-[8px] text-slate-700">{investigation.evidence.length}</span>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {investigation.evidence.map((item) => <TraceEvidenceCard key={item.id} item={item} compact />)}
              </div>
            </div>
          ) : null}
          {investigation.warnings.length > 0 ? (
            <ul className="mt-3 space-y-1 rounded-lg border border-amber-400/15 bg-amber-400/[0.04] px-3 py-2 text-[8px] leading-4 text-amber-200/65">
              {investigation.warnings.map((warning) => <li key={warning}>{warning}</li>)}
            </ul>
          ) : null}
          <div className="mt-3 text-[8px] font-semibold uppercase tracking-[0.12em] text-slate-700">Source · {investigation.source}</div>
        </div>
      ) : null}

      {!selectedNode ? (
        <StatePanel title="Select a causal node" description="Choose a node in the graph to inspect its span, attributes, logs, and direct SigNoz link." compact />
      ) : (
        <>
          <div className="border-b border-white/[0.06] px-5 py-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-[8px] font-bold uppercase tracking-[0.14em] text-slate-600">{selectedNode.kind.replaceAll("_", " ")}</div>
                <h3 className="mt-1.5 truncate text-sm font-semibold text-white">{selectedNode.label}</h3>
                {selectedNode.description ? <p className="mt-2 text-[10px] leading-4 text-slate-500">{selectedNode.description}</p> : null}
              </div>
              {selectedNode.status ? <Badge tone={selectedNode.status.toLowerCase().match(/violation|unsafe|untrusted/) ? "danger" : "neutral"}>{selectedNode.status}</Badge> : null}
            </div>
            <dl className="mt-4 grid grid-cols-2 gap-3 rounded-xl border border-white/[0.055] bg-black/10 p-3">
              <div className="min-w-0">
                <dt className="flex items-center gap-1.5 text-[8px] font-bold uppercase tracking-[0.12em] text-slate-700"><Fingerprint className="h-2.5 w-2.5" /> Trace</dt>
                <dd className="mt-1.5"><CopyIdentifier value={selectedNode.traceId} label="trace ID" /></dd>
              </div>
              <div className="min-w-0">
                <dt className="flex items-center gap-1.5 text-[8px] font-bold uppercase tracking-[0.12em] text-slate-700"><Fingerprint className="h-2.5 w-2.5" /> Span</dt>
                <dd className="mt-1.5"><CopyIdentifier value={selectedNode.spanId} label="span ID" /></dd>
              </div>
              <div className="col-span-2 min-w-0 border-t border-white/[0.055] pt-3">
                <dt className="flex items-center gap-1.5 text-[8px] font-bold uppercase tracking-[0.12em] text-slate-700"><Clock3 className="h-2.5 w-2.5" /> Observed</dt>
                <dd className="mt-1.5 text-[9px] text-slate-400">{formatDateTime(selectedNode.timestamp)}</dd>
              </div>
            </dl>
          </div>

          <div className="flex border-b border-white/[0.06] px-2" role="tablist" aria-label="Evidence views">
            {tabs.map(({ id, label, icon: Icon, count }) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={tab === id}
                onClick={() => setTab(id)}
                className={cn(
                  "relative flex flex-1 items-center justify-center gap-1.5 px-2 py-3 text-[9px] font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-signal-400/50",
                  tab === id ? "text-slate-200 after:absolute after:inset-x-3 after:bottom-0 after:h-px after:bg-signal-400" : "text-slate-600 hover:text-slate-400",
                )}
              >
                <Icon className="h-3 w-3" /> {label}
                {count ? <span className="numeric rounded-full bg-white/[0.06] px-1.5 text-[7px] text-slate-500">{count}</span> : null}
              </button>
            ))}
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {tab === "evidence" ? (
              nodeEvidence.length > 0 ? (
                <div className="space-y-2.5">
                  {nodeEvidence.map((item) => (
                    <TraceEvidenceCard key={item.id} item={item} />
                  ))}
                </div>
              ) : (
                <div className="py-8 text-center text-[10px] leading-5 text-slate-600">
                  {localEvidence
                    ? "This span comes from durable local evidence. Inspect its recorded attributes and logs."
                    : "This span is the evidence. Inspect its attributes or open the complete trace in SigNoz."}
                </div>
              )
            ) : null}
            {tab === "attributes" ? (
              attributes.length > 0 ? (
                <dl className="divide-y divide-white/[0.05] overflow-hidden rounded-xl border border-white/[0.06] bg-black/10">
                  {attributes.map(([key, value]) => (
                    <div key={key} className="px-3 py-2.5">
                      <dt className="break-all font-mono text-[8px] text-sky-300/65">{key}</dt>
                      <dd className="mt-1 break-words font-mono text-[8px] leading-4 text-slate-400">{stringifyAttribute(value)}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <div className="py-8 text-center text-[10px] text-slate-600">No span attributes were returned for this node.</div>
              )
            ) : null}
            {tab === "logs" ? (
              selectedNode.logs.length > 0 ? (
                <div className="space-y-2">
                  {selectedNode.logs.map((log, index) => (
                    <div key={`${log.timestamp}-${index}`} className="rounded-xl border border-white/[0.06] bg-black/10 p-3">
                      <div className="flex items-center justify-between gap-3 text-[7px] font-bold uppercase tracking-[0.11em] text-slate-700">
                        <span>{log.severity ?? "INFO"}</span><span>{formatDateTime(log.timestamp)}</span>
                      </div>
                      <p className="mt-2 font-mono text-[8px] leading-4 text-slate-400">{log.body}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="py-8 text-center text-[10px] text-slate-600">No correlated log records were returned for this span.</div>
              )
            ) : null}
          </div>

          <div className="border-t border-white/[0.06] p-4">
            {traceUrl ? (
              <a href={traceUrl} target="_blank" rel="noreferrer" className={buttonStyles({ variant: "secondary", size: "sm", className: "w-full" })}>
                {localEvidence ? "Open configured trace view" : "Open this trace in SigNoz"} <ExternalLink className="h-3.5 w-3.5" />
              </a>
            ) : (
              <div className="text-center text-[9px] text-slate-700">A trace link is unavailable for this node.</div>
            )}
          </div>
        </>
      )}
    </Panel>
  );
}
