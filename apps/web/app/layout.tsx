import type { Metadata, Viewport } from "next";

import { AppShell } from "@/components/app-shell";

import "@xyflow/react/dist/style.css";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "RecallRoot — Agent memory safety",
    template: "%s · RecallRoot",
  },
  description: "Cross-session causal debugging and remediation for stateful AI agents.",
  applicationName: "RecallRoot",
};

export const viewport: Viewport = {
  colorScheme: "dark",
  themeColor: "#080A0F",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
