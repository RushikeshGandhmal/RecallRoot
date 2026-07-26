import {
  ArrowRight,
  Check,
  ExternalLink,
  Microscope,
  Play,
  ShieldOff,
} from "lucide-react";
import Link from "next/link";

import type { Incident } from "@/lib/api/types";
import { cn } from "@/lib/utils";

import { Button, buttonStyles } from "../ui/button";
import { isLocalEvidenceSource } from "../ui/evidence-source-badge";

interface RemediationBarProps {
  incident: Incident;
  investigated: boolean;
  investigationSource?: string;
  mcpVerified: boolean;
  quarantined: boolean;
  action: "investigating" | "quarantining" | "replaying" | null;
  onInvestigate: () => void;
  onQuarantine: () => void;
  onReplay: () => void;
}

export function RemediationBar({
  incident,
  investigated,
  investigationSource,
  mcpVerified,
  quarantined,
  action,
  onInvestigate,
  onQuarantine,
  onReplay,
}: RemediationBarProps) {
  const remediated = ["remediated", "closed"].includes(incident.status);
  const investigationAttempted = Boolean(investigationSource);
  const degradedInvestigation =
    investigationAttempted && isLocalEvidenceSource(investigationSource ?? "");
  return (
    <div className="sticky bottom-3 z-20 mt-5 overflow-hidden rounded-2xl border border-white/[0.1] bg-ink-900/95 shadow-[0_22px_70px_rgba(0,0,0,.42)] backdrop-blur-2xl">
      <div className="flex flex-col gap-4 p-4 sm:p-5 2xl:flex-row 2xl:items-center 2xl:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold text-slate-200">Remediation sequence</span>
            <div className="hidden h-px w-5 bg-white/[0.1] sm:block" />
            <ol className="flex flex-wrap items-center gap-1.5" aria-label="Remediation progress">
              {[
                { label: "Investigate", done: investigated },
                { label: "Quarantine", done: quarantined },
                { label: "Replay", done: remediated },
              ].map((step, index) => (
                <li key={step.label} className="flex items-center gap-1.5">
                  {index > 0 ? <ArrowRight className="h-2.5 w-2.5 text-slate-700" /> : null}
                  <span className={cn("inline-flex h-5 items-center gap-1 rounded-full border px-2 text-[8px] font-bold uppercase tracking-[0.09em]", step.done ? "border-signal-400/20 bg-signal-400/[0.08] text-signal-300" : "border-white/[0.07] bg-white/[0.025] text-slate-600")}>
                    {step.done ? <Check className="h-2.5 w-2.5" /> : null}{step.label}
                  </span>
                </li>
              ))}
            </ol>
          </div>
          <p className="mt-1.5 max-w-2xl text-[10px] leading-4 text-slate-600">
            {quarantined
              ? "Unsafe memory is isolated. Replay the exact request to verify the agent now requests manager approval."
              : "Confirm the cause from telemetry, then isolate the influencing memory before replaying the request."}
          </p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button
            onClick={onInvestigate}
            loading={action === "investigating"}
            disabled={action !== null || mcpVerified}
            title={
              degradedInvestigation
                ? "Retry after SigNoz finishes ingesting the linked traces"
                : undefined
            }
          >
            {mcpVerified ? <Check className="h-3.5 w-3.5" /> : <Microscope className="h-3.5 w-3.5" />}
            {mcpVerified
              ? "MCP cause verified"
              : investigationAttempted
                ? "Retry with MCP"
                : "Investigate cause"}
          </Button>
          <Button variant="danger" onClick={onQuarantine} loading={action === "quarantining"} disabled={action !== null || quarantined || remediated}>
            {quarantined ? <Check className="h-3.5 w-3.5" /> : <ShieldOff className="h-3.5 w-3.5" />}
            {quarantined ? "Memory quarantined" : "Quarantine memory"}
          </Button>
          {remediated ? (
            <Link href={`/incidents/${encodeURIComponent(incident.id)}/comparison`} className={buttonStyles({ variant: "primary" })}>
              View comparison <ExternalLink className="h-3.5 w-3.5" />
            </Link>
          ) : (
            <Button variant="primary" onClick={onReplay} loading={action === "replaying"} disabled={action !== null || !quarantined} title={!quarantined ? "Quarantine the unsafe memory before replaying" : undefined}>
              <Play className="h-3.5 w-3.5 fill-current" /> Replay request
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
