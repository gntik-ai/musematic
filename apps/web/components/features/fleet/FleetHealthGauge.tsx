"use client";

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { ScoreGauge } from "@/components/shared/ScoreGauge";
import { Skeleton } from "@/components/ui/skeleton";
import { useFleetHealth } from "@/lib/hooks/use-fleet-health";
import type { FleetHealthProjection } from "@/lib/types/fleet";

interface FleetHealthGaugeProps {
  fleetId: string;
  size?: "sm" | "lg";
  showBreakdown?: boolean;
}

function buildBreakdownSummary(health: FleetHealthProjection): string {
  const topMembers = [...health.member_statuses]
    .sort((left, right) => right.health_pct - left.health_pct)
    .slice(0, 3)
    .map((member) => `${member.agent_fqn}: ${member.health_pct}%`)
    .join(", ");

  return [
    `Quorum met: ${health.quorum_met ? "yes" : "no"}.`,
    `Available members: ${health.available_count}/${health.total_count}.`,
    topMembers ? `Top member health: ${topMembers}.` : null,
  ]
    .filter(Boolean)
    .join(" ");
}

export function FleetHealthGauge({
  fleetId,
  size = "lg",
  showBreakdown = true,
}: FleetHealthGaugeProps) {
  const healthQuery = useFleetHealth(fleetId);

  if (healthQuery.isLoading || !healthQuery.data) {
    return (
      <div className="space-y-3">
        <Skeleton className={size === "lg" ? "h-40 w-40 rounded-full" : "h-20 w-20 rounded-full"} />
        <Skeleton className="h-4 w-28" />
      </div>
    );
  }

  const tooltipSummary = buildBreakdownSummary(healthQuery.data);

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger>
          <div title={showBreakdown ? tooltipSummary : undefined}>
            <ScoreGauge
              score={Math.round(healthQuery.data.health_pct)}
              size={size === "lg" ? 160 : 80}
              thresholds={{ warning: 40, good: 70 }}
              {...(size === "lg" ? { label: "Fleet health" } : {})}
            />
          </div>
        </TooltipTrigger>
        {showBreakdown ? (
          <TooltipContent>
            <span>{tooltipSummary}</span>
          </TooltipContent>
        ) : null}
      </Tooltip>
    </TooltipProvider>
  );
}
