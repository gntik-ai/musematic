"use client";

import { use } from "react";
import { GovernanceChainEditor } from "@/components/features/governance/governance-chain-editor";

interface FleetSettingsPageProps {
  params: Promise<{ fleetId: string }>;
}

export default function FleetSettingsPage({ params }: FleetSettingsPageProps) {
  const { fleetId } = use(params);
  return <GovernanceChainEditor scope={{ kind: "fleet", fleetId }} />;
}
