"use client";

import { useState } from "react";
import { RotateCcw, ShieldOff, Shuffle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAdminSubscription,
  useAdminSubscriptionUsage,
  useMigrateSubscription,
  useReactivateSubscription,
  useSuspendSubscription,
} from "@/lib/hooks/use-admin-subscriptions";
import { SubscriptionStatusBadge } from "./SubscriptionStatusBadge";

export function SubscriptionDetailPanel({ id }: { id: string }) {
  const subscription = useAdminSubscription(id);
  const usage = useAdminSubscriptionUsage(id);
  const suspend = useSuspendSubscription();
  const reactivate = useReactivateSubscription();
  const migrate = useMigrateSubscription();
  const [targetPlan, setTargetPlan] = useState("");
  const [targetVersion, setTargetVersion] = useState("1");

  if (subscription.isLoading) {
    return <Skeleton className="h-96 w-full" />;
  }
  if (!subscription.data) {
    return null;
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
      <Card>
        <CardHeader>
          <CardTitle>Status timeline</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <div className="text-muted-foreground">Status</div>
              <SubscriptionStatusBadge status={subscription.data.status} />
            </div>
            <div>
              <div className="text-muted-foreground">Plan pin</div>
              <div className="font-medium">
                {subscription.data.plan_slug} v{subscription.data.plan_version}
              </div>
            </div>
            <div>
              <div className="text-muted-foreground">Period end</div>
              <div className="font-medium">
                {new Date(subscription.data.current_period_end).toLocaleString()}
              </div>
            </div>
          </div>
          <div className="rounded-md border">
            {(usage.data?.items ?? []).map((item) => (
              <div
                key={`${item.metric}-${item.period_start}-${item.is_overage}`}
                className="flex items-center justify-between border-b px-3 py-2 last:border-b-0"
              >
                <span>
                  {item.metric}
                  {item.is_overage ? " overage" : ""}
                </span>
                <span className="font-medium">{item.quantity}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Actions</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              disabled={suspend.isPending}
              onClick={() => suspend.mutate({ id, reason: "admin_action" })}
            >
              <ShieldOff className="h-4 w-4" />
              Suspend
            </Button>
            <Button
              variant="outline"
              disabled={reactivate.isPending}
              onClick={() => reactivate.mutate(id)}
            >
              <RotateCcw className="h-4 w-4" />
              Reactivate
            </Button>
          </div>
          <div className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="target-plan">Plan slug</Label>
              <Input
                id="target-plan"
                value={targetPlan}
                onChange={(event) => setTargetPlan(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="target-version">Plan version</Label>
              <Input
                id="target-version"
                inputMode="numeric"
                value={targetVersion}
                onChange={(event) => setTargetVersion(event.target.value)}
              />
            </div>
            <Button
              className="w-full"
              disabled={migrate.isPending || !targetPlan}
              onClick={() =>
                migrate.mutate({
                  subscriptionId: id,
                  plan_slug: targetPlan,
                  plan_version: Number(targetVersion),
                  reason: "admin_migration",
                })
              }
            >
              <Shuffle className="h-4 w-4" />
              Migrate version
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
