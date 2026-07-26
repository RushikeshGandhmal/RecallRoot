import { cn } from "@/lib/utils";

export function BrandMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 40 40"
      className={cn("h-9 w-9", className)}
      role="img"
      aria-label="RecallRoot"
      fill="none"
    >
      <rect x="1" y="1" width="38" height="38" rx="11" fill="#121A25" stroke="rgba(126,242,188,.24)" />
      <circle cx="13" cy="12" r="3" fill="#7EF2BC" />
      <circle cx="27" cy="12" r="3" fill="#7EF2BC" fillOpacity=".7" />
      <circle cx="20" cy="27.5" r="3.25" fill="#F45B69" />
      <path d="M15.7 13.8 18.5 17M24.4 13.8 21.6 17M20 20v4.2" stroke="#B6FFDC" strokeWidth="2" strokeLinecap="round" />
      <path d="M18.5 17h3.1" stroke="#B6FFDC" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
