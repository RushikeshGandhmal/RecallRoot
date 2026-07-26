"use client";

import {
  Activity,
  ArrowUpRight,
  GitBranch,
  LayoutDashboard,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api/client";
import type { ReadinessStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";

import { BrandMark } from "./brand-mark";
import { Badge } from "./ui/badge";

const signozUrl = process.env.NEXT_PUBLIC_SIGNOZ_URL ?? "http://localhost:3301";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [serviceState, setServiceState] = useState<
    "checking" | "verified" | "degraded" | "offline"
  >("checking");
  const [readiness, setReadiness] = useState<ReadinessStatus | null>(null);

  useEffect(() => {
    let mounted = true;
    const checkHealth = async () => {
      try {
        const readiness = await api.readiness();
        if (mounted) {
          setReadiness(readiness);
          setServiceState(readiness.status === "ready" ? "verified" : "degraded");
        }
      } catch {
        if (mounted) {
          setReadiness(null);
          setServiceState("offline");
        }
      }
    };
    void checkHealth();
    const interval = window.setInterval(checkHealth, 30_000);
    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, []);

  const decisionLabel = readiness
    ? readiness.llm.provider === "ollama"
      ? `Local Ollama · ${readiness.llm.model ?? "model unknown"}`
      : "Deterministic fail-safe"
    : null;

  const navItems = [
    { label: "Control room", href: "/", icon: LayoutDashboard, active: pathname === "/" },
    {
      label: "Causal incidents",
      href: pathname.startsWith("/incidents/") ? pathname : "/#incidents",
      icon: GitBranch,
      active: pathname.startsWith("/incidents/"),
    },
  ];

  return (
    <div className="min-h-screen text-slate-100">
      <div className="pointer-events-none fixed inset-0 -z-10 bg-[radial-gradient(circle_at_76%_-8%,rgba(69,219,156,0.11),transparent_33%),radial-gradient(circle_at_8%_72%,rgba(65,100,180,0.07),transparent_28%)]" />

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 hidden border-r border-white/[0.065] bg-ink-950/88 backdrop-blur-2xl transition-[width] duration-300 lg:flex lg:flex-col",
          collapsed ? "w-[76px]" : "w-[232px]",
        )}
      >
        <div className={cn("flex h-[76px] items-center border-b border-white/[0.055]", collapsed ? "justify-center px-3" : "px-5")}>
          <Link href="/" className="flex items-center gap-3 rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-400/70">
            <BrandMark className="shrink-0" />
            {!collapsed ? (
              <div>
                <div className="text-[15px] font-bold tracking-[-0.02em] text-white">RecallRoot</div>
                <div className="mt-0.5 text-[9px] font-semibold uppercase tracking-[0.19em] text-signal-400/75">Memory safety</div>
              </div>
            ) : null}
          </Link>
        </div>

        <nav className="flex-1 space-y-1.5 px-3 py-5" aria-label="Primary navigation">
          {!collapsed ? <div className="mb-3 px-2 text-[9px] font-bold uppercase tracking-[0.2em] text-slate-600">Workspace</div> : null}
          {navItems.map(({ label, href, icon: Icon, active }) => (
            <Link
              key={label}
              href={href}
              title={collapsed ? label : undefined}
              className={cn(
                "group flex h-10 items-center gap-3 rounded-xl px-3 text-xs font-semibold transition",
                active
                  ? "bg-signal-400/[0.095] text-signal-300 shadow-[inset_0_0_0_1px_rgba(126,242,188,.1)]"
                  : "text-slate-500 hover:bg-white/[0.04] hover:text-slate-200",
                collapsed && "justify-center",
              )}
            >
              <Icon className="h-[17px] w-[17px] shrink-0" aria-hidden="true" />
              {!collapsed ? label : <span className="sr-only">{label}</span>}
            </Link>
          ))}
          <a
            href={signozUrl}
            target="_blank"
            rel="noreferrer"
            title={collapsed ? "Open SigNoz" : undefined}
            className={cn(
              "group flex h-10 items-center gap-3 rounded-xl px-3 text-xs font-semibold text-slate-500 transition hover:bg-white/[0.04] hover:text-slate-200",
              collapsed && "justify-center",
            )}
          >
            <Activity className="h-[17px] w-[17px] shrink-0" aria-hidden="true" />
            {!collapsed ? (
              <>
                <span>Open SigNoz</span>
                <ArrowUpRight className="ml-auto h-3.5 w-3.5 opacity-45" aria-hidden="true" />
              </>
            ) : (
              <span className="sr-only">Open SigNoz</span>
            )}
          </a>
        </nav>

        <div className="border-t border-white/[0.055] p-3">
          {!collapsed ? (
            <div className="mb-3 rounded-xl border border-white/[0.06] bg-white/[0.025] px-3 py-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-semibold text-slate-400">Agent telemetry</span>
                <Badge
                  tone={
                    serviceState === "verified"
                      ? "success"
                      : serviceState === "offline"
                        ? "danger"
                        : serviceState === "degraded"
                          ? "warning"
                          : "neutral"
                  }
                  dot
                  className="h-5 px-2 text-[8px]"
                >
                  {serviceState === "verified" ? "SigNoz verified" : serviceState}
                </Badge>
              </div>
              <p className="mt-2 text-[10px] leading-4 text-slate-500">
                {serviceState === "verified"
                  ? `${decisionLabel}. API, OTLP, Query Builder, and MCP are ready.`
                  : serviceState === "degraded"
                    ? `${decisionLabel ? `${decisionLabel}. ` : ""}One or more evidence checks need attention.`
                    : serviceState === "offline"
                      ? "RecallRoot API is unreachable."
                      : "Checking the complete evidence path…"}
              </p>
            </div>
          ) : null}
          <button
            type="button"
            onClick={() => setCollapsed((value) => !value)}
            className="flex h-9 w-full items-center justify-center gap-2 rounded-lg text-[10px] font-semibold text-slate-600 transition hover:bg-white/[0.04] hover:text-slate-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-400/60"
            aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
          >
            {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
            {!collapsed ? "Collapse" : null}
          </button>
        </div>
      </aside>

      <div className={cn("transition-[padding] duration-300", collapsed ? "lg:pl-[76px]" : "lg:pl-[232px]")}>
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-white/[0.06] bg-ink-950/75 px-4 backdrop-blur-xl sm:px-6 lg:hidden">
          <Link href="/" className="flex items-center gap-2.5">
            <BrandMark className="h-8 w-8" />
            <span className="text-sm font-bold text-white">RecallRoot</span>
          </Link>
          <div className="flex items-center gap-1">
            <Link href="/" className="rounded-lg p-2 text-slate-400 hover:bg-white/[0.05] hover:text-white" aria-label="Control room">
              <LayoutDashboard className="h-4 w-4" />
            </Link>
            <a href={signozUrl} target="_blank" rel="noreferrer" className="rounded-lg p-2 text-slate-400 hover:bg-white/[0.05] hover:text-white" aria-label="Open SigNoz">
              <Activity className="h-4 w-4" />
            </a>
          </div>
        </header>
        <main className="mx-auto min-h-screen w-full max-w-[1600px] px-4 pb-10 pt-6 sm:px-6 lg:px-8 lg:pt-8 xl:px-10">{children}</main>
      </div>
    </div>
  );
}
