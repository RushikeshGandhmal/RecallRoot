import { AlertTriangle, DatabaseZap, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "./button";

interface StatePanelProps {
  title: string;
  description: string;
  kind?: "empty" | "error";
  action?: ReactNode;
  onRetry?: () => void;
  compact?: boolean;
}

export function StatePanel({
  title,
  description,
  kind = "empty",
  action,
  onRetry,
  compact = false,
}: StatePanelProps) {
  const Icon = kind === "error" ? AlertTriangle : DatabaseZap;
  return (
    <div
      className={`flex flex-col items-center justify-center text-center ${compact ? "min-h-48 px-5 py-8" : "min-h-[320px] px-6 py-12"}`}
      role={kind === "error" ? "alert" : "status"}
    >
      <div className={`grid place-items-center rounded-2xl border ${kind === "error" ? "border-danger-400/20 bg-danger-500/10 text-danger-300" : "border-white/10 bg-white/[0.04] text-slate-400"} ${compact ? "h-10 w-10" : "h-12 w-12"}`}>
        <Icon className={compact ? "h-4 w-4" : "h-5 w-5"} aria-hidden="true" />
      </div>
      <h3 className="mt-4 text-sm font-semibold text-slate-100">{title}</h3>
      <p className="mt-1.5 max-w-md text-sm leading-6 text-slate-500">{description}</p>
      <div className="mt-5 flex flex-wrap justify-center gap-2">
        {onRetry ? (
          <Button onClick={onRetry} size="sm">
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            Try again
          </Button>
        ) : null}
        {action}
      </div>
    </div>
  );
}
