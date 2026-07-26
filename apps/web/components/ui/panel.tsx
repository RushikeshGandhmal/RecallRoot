import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function Panel({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-white/[0.075] bg-ink-900/85 shadow-panel backdrop-blur-xl",
        className,
      )}
      {...props}
    />
  );
}
