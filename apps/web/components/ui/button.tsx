import { LoaderCircle } from "lucide-react";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";
type ButtonSize = "sm" | "md" | "lg";

const variants: Record<ButtonVariant, string> = {
  primary:
    "border-signal-400 bg-signal-400 text-ink-950 shadow-[0_10px_32px_rgba(69,219,156,0.15)] hover:border-signal-300 hover:bg-signal-300",
  secondary:
    "border-white/10 bg-white/[0.055] text-slate-100 hover:border-white/20 hover:bg-white/[0.09]",
  danger:
    "border-danger-500/45 bg-danger-500/10 text-danger-300 hover:border-danger-400/70 hover:bg-danger-500/16",
  ghost: "border-transparent bg-transparent text-slate-400 hover:bg-white/[0.055] hover:text-slate-100",
};

const sizes: Record<ButtonSize, string> = {
  sm: "h-9 gap-2 rounded-lg px-3 text-xs",
  md: "h-10 gap-2 rounded-xl px-4 text-sm",
  lg: "h-12 gap-2.5 rounded-xl px-5 text-sm",
};

export function buttonStyles({
  variant = "secondary",
  size = "md",
  className,
}: {
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
} = {}): string {
  return cn(
    "inline-flex items-center justify-center whitespace-nowrap border font-semibold transition duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-ink-950 disabled:pointer-events-none disabled:opacity-45",
    variants[variant],
    sizes[size],
    className,
  );
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

export function Button({
  children,
  className,
  variant = "secondary",
  size = "md",
  loading = false,
  disabled,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={buttonStyles({ variant, size, className })}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
      {children}
    </button>
  );
}
