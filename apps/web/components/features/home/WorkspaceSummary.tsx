"use client";

import { useMemo } from "react";
import { MetricCard, type TrendDirection } from "@/components/shared/MetricCard";
import { SectionError } from "@/components/features/home/SectionError";
import { useWorkspaceSummary } from "@/lib/hooks/use-home-data";
import type { MetricCardData } from "@/lib/types/home";

interface WorkspaceSummaryProps {
  workspaceId: string;
  isConnected?: boolean;
}

type MetricChangeDirection = NonNullable<MetricCardData["change"]>["direction"];

function formatCurrency(cents: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(cents / 100);
}

function toChangeDirection(delta: number): MetricChangeDirection {
  if (delta > 0) {
    return "up";
  }

  if (delta < 0) {
    return "down";
  }

  return "stable";
}

function toTrend(direction: MetricChangeDirection): TrendDirection {
  if (direction === "stable") {
    return "neutral";
  }

  return direction;
}

function formatDelta(direction: MetricChangeDirection, delta: number): string {
  if (direction === "stable") {
    return "Stable";
  }

  return `${delta > 0 ? "+" : ""}${delta}`;
}

function buildAriaLabel(card: MetricCardData): string {
  if (!card.change) {
    return `${card.label}: ${card.value}`;
  }

  if (card.change.direction === "stable") {
    return `${card.label}: ${card.value}, stable`;
  }

  return `${card.label}: ${card.value}, ${
    card.change.direction === "up" ? "increased" : "decreased"
  } by ${card.change.delta}`;
}

export function WorkspaceSummary({
  workspaceId,
  isConnected,
}: WorkspaceSummaryProps) {
  const { data, error, isError, isLoading, refetch } = useWorkspaceSummary(
    workspaceId,
    { isConnected },
  );

  const cards = useMemo<MetricCardData[]>(() => {
    if (!data) {
      return [];
    }

    const costDelta = data.cost_current - data.cost_previous;
    const costDirection = toChangeDirection(costDelta);

    return [
      {
        id: "active_agents",
        label: "Active Agents",
        value: data.active_agents,
        change: {
          direction: toChangeDirection(data.active_agents_change),
          delta: Math.abs(data.active_agents_change),
        },
      },
      {
        id: "running_executions",
        label: "Running Executions",
        value: data.running_executions,
        change: {
          direction: toChangeDirection(data.running_executions_change),
          delta: Math.abs(data.running_executions_change),
        },
      },
      {
        id: "pending_approvals",
        label: "Pending Approvals",
        value: data.pending_approvals,
        change: {
          direction: toChangeDirection(data.pending_approvals_change),
          delta: Math.abs(data.pending_approvals_change),
        },
      },
      {
        id: "cost",
        label: `Cost (${data.period_label})`,
        value: formatCurrency(data.cost_current),
        change: {
          direction: costDirection,
          delta:
            costDirection === "stable"
              ? "0"
              : formatCurrency(Math.abs(costDelta)),
        },
      },
    ];
  }, [data]);

  if (isError) {
    return (
      <SectionError
        message={error instanceof Error ? error.message : undefined}
        onRetry={() => {
          void refetch();
        }}
        title="Workspace summary unavailable"
      />
    );
  }

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <MetricCard
            key={index}
            isLoading
            title="Loading"
            value="--"
          />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => {
        const direction = card.change?.direction ?? "stable";
        const delta = card.change?.delta ?? 0;
        const trendValue =
          card.change === null
            ? undefined
            : direction === "stable"
              ? "Stable"
              : card.id === "cost"
                ? `${direction === "up" ? "+" : "-"}${delta}`
                : formatDelta(direction, Number(delta));

        return (
          <div
            key={card.id}
            aria-label={buildAriaLabel(card)}
            role="group"
          >
            <MetricCard
              title={card.label}
              trend={toTrend(direction)}
              trendValue={trendValue}
              value={card.value}
            />
          </div>
        );
      })}
    </div>
  );
}
