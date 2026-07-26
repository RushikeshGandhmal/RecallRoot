import type { Metadata } from "next";

import { IncidentWorkspace } from "@/components/incident-panel/incident-workspace";

export const metadata: Metadata = {
  title: "Incident investigation",
};

export default async function IncidentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <IncidentWorkspace incidentId={decodeURIComponent(id)} />;
}
