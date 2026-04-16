"use client";

import { ScoreGauge } from "@/components/shared/ScoreGauge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAgentHealth } from "@/lib/hooks/use-agent-health";

export interface AgentHealthScoreGaugeProps {
  fqn: string;
  showBreakdown?: boolean;
  size?: "sm" | "lg";
}

export function AgentHealthScoreGauge({
  fqn,
  showBreakdown = true,
  size = "lg",
}: AgentHealthScoreGaugeProps) {
  const healthQuery = useAgentHealth(fqn);

  if (healthQuery.isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className={size === "sm" ? "h-20 w-20 rounded-full" : "h-40 w-40 rounded-full"} />
        <Skeleton className="h-4 w-28" />
      </div>
    );
  }

  const score = healthQuery.data?.composite_score ?? 0;
  const gaugeSize = size === "sm" ? 80 : 160;

  return (
    <div className="space-y-4">
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger>
            <div>
              <ScoreGauge
                label="Composite health"
                score={score}
                size={gaugeSize}
                thresholds={{ warning: 40, good: 71 }}
              />
            </div>
          </TooltipTrigger>
          {showBreakdown ? (
            <TooltipContent>
              {healthQuery.data?.components.map((component) => (
                <span key={component.label}>
                  {component.label}: {component.score}
                </span>
              ))}
            </TooltipContent>
          ) : null}
        </Tooltip>
      </TooltipProvider>
      {showBreakdown && healthQuery.data?.components?.length ? (
        <div className="grid gap-2 md:grid-cols-2">
          {healthQuery.data.components.map((component) => (
            <div
              key={component.label}
              className="rounded-xl border border-border/60 bg-background/70 px-3 py-2 text-sm"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="text-muted-foreground">{component.label}</span>
                <span className="font-semibold">{component.score}</span>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
