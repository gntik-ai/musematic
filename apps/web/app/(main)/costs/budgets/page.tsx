"use client";

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { BudgetConfigForm } from "@/components/features/cost-governance/BudgetConfigForm";
import { BudgetThresholdGauge } from "@/components/features/cost-governance/BudgetThresholdGauge";
import { OverrideDialog } from "@/components/features/cost-governance/OverrideDialog";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import {
  deleteBudget,
  useBudgetAlerts,
  useIssueOverride,
  useSaveBudget,
  useWorkspaceBudgets,
  useWorkspaceCostSummary,
} from "@/lib/api/costs";
import { useWorkspaceStore } from "@/store/workspace-store";

export default function CostBudgetsPage() {
  const workspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const budgets = useWorkspaceBudgets(workspaceId);
  const alerts = useBudgetAlerts(workspaceId);
  const summary = useWorkspaceCostSummary(workspaceId);
  const saveBudget = useSaveBudget(workspaceId);
  const issueOverride = useIssueOverride(workspaceId);
  const [open, setOpen] = useState(false);

  if (!workspaceId) {
    return <EmptyState title="Budgets unavailable" description="Select a workspace." />;
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Cost Budgets</h1>
        <div className="flex flex-wrap gap-2">
          <OverrideDialog
            isSubmitting={issueOverride.isPending}
            override={issueOverride.data ?? null}
            onIssue={(reason) => issueOverride.mutate(reason)}
          />
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <Button>
                <Plus className="mr-2 h-4 w-4" />
                Budget
              </Button>
            </SheetTrigger>
            <SheetContent>
              <div className="flex flex-col gap-2 text-left">
                <SheetTitle>Budget</SheetTitle>
              </div>
              <div className="mt-6">
                <BudgetConfigForm
                  isSubmitting={saveBudget.isPending}
                  onSubmit={(payload) => {
                    saveBudget.mutate(payload, { onSuccess: () => setOpen(false) });
                  }}
                />
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {budgets.data?.length ? (
          budgets.data.map((budget) => (
            <Card key={budget.id}>
              <CardHeader className="flex flex-row items-center justify-between gap-4">
                <CardTitle className="text-base capitalize">{budget.period_type}</CardTitle>
                <Button
                  aria-label={`Delete ${budget.period_type} budget`}
                  size="icon"
                  variant="ghost"
                  onClick={() => {
                    void deleteBudget(workspaceId, budget.period_type);
                  }}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </CardHeader>
              <CardContent>
                <BudgetThresholdGauge
                  budgetCents={budget.budget_cents}
                  currentSpendCents={summary.data?.total_cost_cents ?? 0}
                  thresholds={budget.soft_alert_thresholds}
                />
              </CardContent>
            </Card>
          ))
        ) : (
          <Card className="lg:col-span-3">
            <CardContent className="p-6">
              <EmptyState title="No budgets" description="Create a workspace budget." />
            </CardContent>
          </Card>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Alert History</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Threshold</TableHead>
                  <TableHead>Spend</TableHead>
                  <TableHead>Triggered</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(alerts.data ?? []).map((alert) => (
                  <TableRow key={alert.id}>
                    <TableCell>{alert.threshold_percentage}%</TableCell>
                    <TableCell>${(Number(alert.spend_cents) / 100).toFixed(2)}</TableCell>
                    <TableCell>{new Date(alert.triggered_at).toLocaleString()}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
