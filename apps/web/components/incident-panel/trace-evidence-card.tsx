import { ExternalLink, Fingerprint } from "lucide-react";

import type { GraphEvidence } from "@/lib/api/types";
import { buildSignozTraceUrl, cn, truncateIdentifier } from "@/lib/utils";

export function TraceEvidenceCard({
  item,
  compact = false,
}: {
  item: GraphEvidence;
  compact?: boolean;
}) {
  const traceUrl = item.signozUrl ?? buildSignozTraceUrl(item.traceId);
  return (
    <div
      className={cn(
        "rounded-xl border border-white/[0.06] bg-white/[0.022]",
        compact ? "p-3" : "p-3.5",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        {traceUrl ? (
          <a
            href={traceUrl}
            target="_blank"
            rel="noreferrer"
            className="group flex min-w-0 items-center gap-1.5 text-[9px] font-semibold text-slate-300 transition hover:text-sky-300"
          >
            <span className="truncate">{item.title}</span>
            <ExternalLink className="h-3 w-3 shrink-0 opacity-55 transition group-hover:opacity-100" />
          </a>
        ) : (
          <div className="truncate text-[9px] font-semibold text-slate-300">{item.title}</div>
        )}
        {item.kind ? (
          <span className="shrink-0 text-[7px] font-bold uppercase tracking-[0.1em] text-slate-600">
            {item.kind}
          </span>
        ) : null}
      </div>
      <p className={cn("text-[9px] leading-4 text-slate-500", compact ? "mt-1.5 line-clamp-1" : "mt-2")}>{item.detail}</p>
      {item.traceId ? (
        <div className="mt-2 flex items-center gap-1.5 font-mono text-[7px] text-slate-700">
          <Fingerprint className="h-2.5 w-2.5" />
          {truncateIdentifier(item.traceId, 5)}
          {item.spanId ? <span>· {truncateIdentifier(item.spanId, 4)}</span> : null}
        </div>
      ) : null}
    </div>
  );
}
