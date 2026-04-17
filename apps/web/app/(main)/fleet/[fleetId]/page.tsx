"use client";

import { use } from "react";
import { FleetDetailView } from "@/components/features/fleet/FleetDetailView";

interface FleetDetailPageProps {
  params: Promise<{
    fleetId: string;
  }>;
}

export default function FleetDetailPage({ params }: FleetDetailPageProps) {
  const { fleetId } = use(params);

  return <FleetDetailView fleetId={fleetId} />;
}
