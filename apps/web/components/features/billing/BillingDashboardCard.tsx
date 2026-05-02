"use client";

import Link from "next/link";
import { AlertTriangle, CreditCard, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspaceBilling } from "@/lib/hooks/use-workspace-billing";
import { BillingPeriodCountdown } from "./BillingPeriodCountdown";
import { PostDowngradeCleanupBanner } from "./PostDowngradeCleanupBanner";
import { QuotaProgressBars } from "./QuotaProgressBars";

interface BillingDashboardCardProps {
  workspaceId: string;
}

export function BillingDashboardCard({ workspaceId }: BillingDashboardCardProps) {
  const billing = useWorkspaceBilling(workspaceId);

  if (billing.isLoading) {
    return <Skeleton className="h-96 rounded-lg" />;
  }

  if (!billing.data) {
    return null;
  }

  const { subscription, plan_caps, usage, forecast, overage, available_actions } = billing.data;
  const cleanup = {
    workspaces:
      subscription.plan_slug === "free"
        ? Math.max(usage.active_workspaces - plan_caps.max_workspaces, 0)
        : 0,
    agents:
      subscription.plan_slug === "free"
        ? Math.max(usage.active_agents_in_this_workspace - plan_caps.max_agents_per_workspace, 0)
        : 0,
    users:
      subscription.plan_slug === "free"
        ? Math.max(usage.active_users_in_this_workspace - plan_caps.max_users_per_workspace, 0)
        : 0,
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
      <Card>
        <CardHeader className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <CardTitle>Billing</CardTitle>
            <Badge variant="secondary">{subscription.plan_slug}</Badge>
          </div>
          {overage.authorization_required && plan_caps.overage_price_per_minute !== "0.0000" ? (
            <div className="flex items-center gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              <AlertTriangle className="h-4 w-4" />
              <span>Overage authorization is required for more work this period.</span>
            </div>
          ) : null}
          {subscription.cancel_at_period_end ? (
            <BillingPeriodCountdown
              workspaceId={workspaceId}
              periodEnd={subscription.current_period_end}
            />
          ) : null}
        </CardHeader>
        <CardContent className="space-y-5">
          <PostDowngradeCleanupBanner
            workspaces={cleanup.workspaces}
            agents={cleanup.agents}
            users={cleanup.users}
          />
          <QuotaProgressBars caps={plan_caps} usage={usage} />
          <div className="grid gap-3 text-sm sm:grid-cols-3">
            <div>
              <div className="text-muted-foreground">Period ends</div>
              <div className="font-medium">{new Date(subscription.current_period_end).toLocaleDateString()}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Forecast minutes</div>
              <div className="font-medium">{forecast.minutes_at_period_end}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Estimated overage</div>
              <div className="font-medium">EUR {forecast.estimated_overage_eur}</div>
            </div>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Actions</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-2 text-sm">
            <CreditCard className="h-4 w-4 text-muted-foreground" />
            <span>Payment method: {billing.data.payment_method.status}</span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <ShieldCheck className="h-4 w-4 text-muted-foreground" />
            <span>Model tier: {plan_caps.allowed_model_tier}</span>
          </div>
          {overage.authorization_required ? (
            <Button asChild className="w-full">
              <Link href={`/workspaces/${workspaceId}/billing/overage-authorize`}>
                Authorise overage
              </Link>
            </Button>
          ) : null}
          {available_actions.includes("upgrade_to_pro") ? (
            <Button asChild className="w-full" variant="outline">
              <Link href={`/workspaces/${workspaceId}/billing/upgrade`}>Upgrade to Pro</Link>
            </Button>
          ) : null}
          {available_actions.includes("downgrade_to_free") ? (
            <Button asChild className="w-full" variant="outline">
              <Link href={`/workspaces/${workspaceId}/billing/downgrade`}>
                Schedule downgrade
              </Link>
            </Button>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
