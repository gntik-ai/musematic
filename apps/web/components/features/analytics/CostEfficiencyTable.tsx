"use client";

import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatUsd, humanizeAnalyticsKey } from "@/lib/analytics";
import type { ScatterPoint } from "@/types/analytics";

export interface CostEfficiencyTableProps {
  agents: ScatterPoint[];
}

export function CostEfficiencyTable({ agents }: CostEfficiencyTableProps) {
  return (
    <div className="overflow-x-auto rounded-[1.25rem] border border-border/60">
      <Table>
        <TableCaption>Showing cost efficiency by agent</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead>Rank</TableHead>
            <TableHead>Agent</TableHead>
            <TableHead>Model</TableHead>
            <TableHead>Cost</TableHead>
            <TableHead>Quality</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {agents
            .slice()
            .sort((left, right) => left.efficiencyRank - right.efficiencyRank)
            .map((agent) => (
              <TableRow key={`${agent.agentFqn}-${agent.modelId}`}>
                <TableCell>{agent.efficiencyRank}</TableCell>
                <TableCell>{humanizeAnalyticsKey(agent.agentFqn)}</TableCell>
                <TableCell>{agent.modelId}</TableCell>
                <TableCell>{formatUsd(agent.costUsd)}</TableCell>
                <TableCell>
                  {agent.qualityScore === null ? "—" : agent.qualityScore.toFixed(2)}
                </TableCell>
              </TableRow>
            ))}
        </TableBody>
      </Table>
    </div>
  );
}
