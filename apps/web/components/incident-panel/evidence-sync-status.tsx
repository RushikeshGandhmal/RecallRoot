import { CloudOff, LoaderCircle, RefreshCw } from "lucide-react";

import { Button } from "../ui/button";

export type EvidenceSyncState = "idle" | "syncing" | "live" | "degraded";

export function EvidenceSyncStatus({
  state,
  onRetry,
}: {
  state: EvidenceSyncState;
  onRetry: () => void;
}) {
  if (state === "idle" || state === "live") return null;

  if (state === "syncing") {
    return (
      <div
        className="flex items-start gap-3 rounded-xl border border-sky-400/20 bg-sky-400/[0.06] px-4 py-3 text-sky-200"
        role="status"
        aria-live="polite"
      >
        <LoaderCircle className="mt-0.5 h-4 w-4 shrink-0 animate-spin" />
        <div>
          <div className="text-[11px] font-semibold">Syncing live SigNoz evidence</div>
          <p className="mt-1 text-[10px] leading-4 text-sky-100/55">
            OpenTelemetry export is asynchronous. RecallRoot is waiting for both session
            traces to become queryable before upgrading the causal graph.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      className="flex flex-col gap-3 rounded-xl border border-amber-400/20 bg-amber-400/[0.055] px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
      role="status"
    >
      <div className="flex items-start gap-3">
        <CloudOff className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
        <div>
          <div className="text-[11px] font-semibold text-amber-200">
            Live evidence is not queryable yet
          </div>
          <p className="mt-1 text-[10px] leading-4 text-amber-100/50">
            The graph is explicitly using validated local evidence. Check the SigNoz API
            key and ingestion health, then retry without recreating the incident.
          </p>
        </div>
      </div>
      <Button variant="secondary" size="sm" onClick={onRetry} className="shrink-0">
        <RefreshCw className="h-3.5 w-3.5" /> Retry SigNoz
      </Button>
    </div>
  );
}
