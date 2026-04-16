"use client";

import { FleetDetailView } from "@/components/features/fleet/FleetDetailView";

interface FleetDetailPageProps {
  params: {
    fleetId: string;
  };
}

export default function FleetDetailPage({ params }: FleetDetailPageProps) {
  return <FleetDetailView fleetId={params.fleetId} />;
}
