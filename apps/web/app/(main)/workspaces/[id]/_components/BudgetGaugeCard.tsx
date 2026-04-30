"use client";

import { WalletCards } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

function numberValue(value: unknown): number {
  return typeof value === "number" ? value : Number(value ?? 0);
}

export function BudgetGaugeCard({ budget }: { budget: Record<string, unknown> }) {
  const limit = numberValue(budget.amount ?? budget.budget_cents ?? budget.limit);
  const spent = numberValue(budget.spent ?? budget.current_spend_cents ?? budget.current);
  const percent = limit > 0 ? Math.min(100, Math.round((spent / limit) * 100)) : 0;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <WalletCards className="h-4 w-4" />
          Budget
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-baseline justify-between">
          <p className="text-3xl font-semibold">{percent}%</p>
          <p className="text-xs text-muted-foreground">{spent} / {limit || "unset"}</p>
        </div>
        <Progress value={percent} />
      </CardContent>
    </Card>
  );
}
