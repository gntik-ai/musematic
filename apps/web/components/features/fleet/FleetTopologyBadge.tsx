"use client";

import { Badge } from "@/components/ui/badge";
import { FLEET_TOPOLOGY_LABELS, type FleetTopologyType } from "@/lib/types/fleet";

interface FleetTopologyBadgeProps {
  topology: FleetTopologyType;
}

export function FleetTopologyBadge({ topology }: FleetTopologyBadgeProps) {
  return (
    <Badge
      className="border-border/80 bg-background/70 text-foreground"
      variant="outline"
    >
      {FLEET_TOPOLOGY_LABELS[topology]}
    </Badge>
  );
}

