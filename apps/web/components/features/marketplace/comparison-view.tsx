"use client";

import Link from "next/link";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  buildAgentHref,
  formatUsdCost,
  humanizeMarketplaceValue,
  type AgentDetail,
} from "@/lib/types/marketplace";

export interface ComparisonViewProps {
  agents: AgentDetail[];
  onRemove: (fqn: string) => void;
}

function valueOrFallback(value: string | null): string {
  return value && value.length > 0 ? value : "—";
}

export function ComparisonView({ agents, onRemove }: ComparisonViewProps) {
  const rows = [
    {
      attribute: "Display Name",
      values: agents.map((agent) => agent.displayName),
    },
    {
      attribute: "Maturity",
      values: agents.map((agent) => humanizeMarketplaceValue(agent.maturityLevel)),
    },
    {
      attribute: "Trust Tier",
      values: agents.map((agent) => humanizeMarketplaceValue(agent.trustTier)),
    },
    {
      attribute: "Capabilities",
      values: agents.map((agent) => valueOrFallback(agent.capabilities.join(", "))),
    },
    {
      attribute: "Average Rating",
      values: agents.map((agent) =>
        agent.averageRating === null ? "—" : agent.averageRating.toFixed(1),
      ),
    },
    {
      attribute: "Cost",
      values: agents.map((agent) =>
        formatUsdCost(agent.costBreakdown.estimatedCostPerInvocationUsd),
      ),
    },
    {
      attribute: "Latest Eval Score",
      values: agents.map((agent) =>
        agent.qualityMetrics.evaluationScore === null
          ? "—"
          : `${Math.round(agent.qualityMetrics.evaluationScore * 100)}%`,
      ),
    },
    {
      attribute: "Active Policies",
      values: agents.map((agent) =>
        agent.policies.length > 0 ? String(agent.policies.length) : "—",
      ),
    },
    {
      attribute: "Certification Badges",
      values: agents.map((agent) =>
        agent.trustSignals.certificationBadges.length > 0
          ? `${agent.trustSignals.certificationBadges.length} certifications`
          : "—",
      ),
    },
  ];

  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <CardTitle>Comparison view</CardTitle>
      </CardHeader>
      <CardContent className="overflow-auto">
        <table className="min-w-full table-fixed border-separate border-spacing-0">
          <thead>
            <tr>
              <th className="w-44 border-b border-border/60 px-4 py-3 text-left text-sm font-semibold">
                Attribute
              </th>
              {agents.map((agent) => (
                <th
                  key={agent.fqn}
                  className="min-w-64 border-b border-border/60 px-4 py-3 text-left align-top"
                >
                  <div className="space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <Link
                          className="font-semibold transition hover:text-brand-accent"
                          href={buildAgentHref(agent.namespace, agent.localName)}
                        >
                          {agent.displayName}
                        </Link>
                        <p className="text-sm text-muted-foreground">{agent.fqn}</p>
                      </div>
                      <Button
                        aria-label={`Remove ${agent.displayName} from comparison`}
                        size="icon"
                        variant="ghost"
                        onClick={() => onRemove(agent.fqn)}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.attribute}>
                <th className="border-b border-border/40 px-4 py-3 text-left text-sm font-medium text-muted-foreground">
                  {row.attribute}
                </th>
                {row.values.map((value, index) => (
                  <td
                    key={`${row.attribute}-${agents[index]?.fqn ?? index}`}
                    className="border-b border-border/40 px-4 py-3 text-sm"
                  >
                    {valueOrFallback(value)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
