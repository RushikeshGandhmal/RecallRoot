import type { Metadata } from "next";

import { ComparisonView } from "@/components/replay-comparison/comparison-view";

export const metadata: Metadata = {
  title: "Replay comparison",
};

export default async function ReplayComparisonPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ComparisonView incidentId={decodeURIComponent(id)} />;
}
