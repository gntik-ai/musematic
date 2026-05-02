"use client";

import type { PlanVersion } from "@/lib/hooks/use-admin-plans";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

const LABELS: Record<string, string> = {
  price_monthly: "Monthly price",
  executions_per_day: "Executions/day",
  executions_per_month: "Executions/month",
  minutes_per_day: "Minutes/day",
  minutes_per_month: "Minutes/month",
  max_workspaces: "Workspaces",
  max_agents_per_workspace: "Agents/workspace",
  max_users_per_workspace: "Users/workspace",
  overage_price_per_minute: "Overage EUR/min",
  trial_days: "Trial days",
  quota_period_anchor: "Period anchor",
};

interface PlanVersionDiffProps {
  fromVersion?: PlanVersion | null;
  toVersion: PlanVersion;
}

function valueFor(version: PlanVersion | null | undefined, field: string): unknown {
  if (!version) {
    return null;
  }
  return version[field as keyof PlanVersion];
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "None";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

export function PlanVersionDiff({ fromVersion, toVersion }: PlanVersionDiffProps) {
  const fields = Object.keys(LABELS);

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Parameter</TableHead>
            <TableHead>Previous</TableHead>
            <TableHead>Selected</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {fields.map((field) => {
            const before = valueFor(fromVersion, field);
            const after = valueFor(toVersion, field);
            const changed = formatValue(before) !== formatValue(after);
            return (
              <TableRow key={field} className={cn(changed && "bg-amber-50/70")}>
                <TableCell className="font-medium">{LABELS[field]}</TableCell>
                <TableCell>{formatValue(before)}</TableCell>
                <TableCell>{formatValue(after)}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
