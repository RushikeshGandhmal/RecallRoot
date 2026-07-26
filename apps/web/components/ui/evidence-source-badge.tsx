import { Database, HardDrive, PlugZap } from "lucide-react";

import { Badge } from "./badge";

export function isLocalEvidenceSource(source: string): boolean {
  return source.toLowerCase().replace(/[ .-]+/g, "_").includes("local_evidence");
}

export function isMcpEvidenceSource(source: string): boolean {
  return source.toLowerCase().replace(/[ .-]+/g, "_") === "signoz_mcp";
}

export function EvidenceSourceBadge({ source }: { source: string }) {
  const normalized = source.toLowerCase().replace(/[ .-]+/g, "_");
  if (isLocalEvidenceSource(source)) {
    return (
      <Badge tone="warning">
        <HardDrive className="h-2.5 w-2.5" /> Local evidence
      </Badge>
    );
  }
  if (isMcpEvidenceSource(source)) {
    return (
      <Badge tone="success" dot>
        <PlugZap className="h-2.5 w-2.5" /> SigNoz MCP
      </Badge>
    );
  }
  if (normalized === "signoz" || normalized === "signoz_telemetry") {
    return (
      <Badge tone="info" dot>
        <Database className="h-2.5 w-2.5" /> SigNoz
      </Badge>
    );
  }
  return <Badge>{source}</Badge>;
}
