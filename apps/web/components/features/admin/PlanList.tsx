"use client";

import Link from "next/link";
import { useState } from "react";
import { Edit3, History, Loader2, Plus } from "lucide-react";
import { PlanEditForm } from "@/components/features/admin/PlanEditForm";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useAdminPlans,
  useUpdatePlanMetadata,
  type AdminPlan,
} from "@/lib/hooks/use-admin-plans";
import { toast } from "@/lib/hooks/use-toast";

function boolText(value: boolean): string {
  return value ? "On" : "Off";
}

function tierVariant(tier: AdminPlan["tier"]) {
  if (tier === "enterprise") {
    return "outline" as const;
  }
  if (tier === "pro") {
    return "secondary" as const;
  }
  return "default" as const;
}

export function PlanList() {
  const { data, error, isLoading } = useAdminPlans();
  const updateMetadata = useUpdatePlanMetadata();
  const [createOpen, setCreateOpen] = useState(false);

  async function toggle(plan: AdminPlan, field: "is_public" | "is_active") {
    await updateMetadata.mutateAsync({
      slug: plan.slug,
      payload: { [field]: !plan[field] },
    });
    toast({ title: "Plan updated", variant: "success" });
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Plans unavailable</AlertTitle>
        <AlertDescription>
          {error instanceof Error ? error.message : "Plan catalogue could not be loaded"}
        </AlertDescription>
      </Alert>
    );
  }

  const plans = data?.items ?? [];

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button size="sm" variant="outline" onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4" />
          Create new plan
        </Button>
      </div>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Slug</TableHead>
              <TableHead>Tier</TableHead>
              <TableHead>Current version</TableHead>
              <TableHead>Subscriptions</TableHead>
              <TableHead>Public</TableHead>
              <TableHead>Active</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {plans.map((plan) => (
              <TableRow key={plan.id}>
                <TableCell>
                  <div className="font-medium">{plan.slug}</div>
                  <div className="text-xs text-muted-foreground">{plan.display_name}</div>
                </TableCell>
                <TableCell>
                  <Badge variant={tierVariant(plan.tier)}>{plan.tier}</Badge>
                </TableCell>
                <TableCell>{plan.current_published_version ?? "Draft only"}</TableCell>
                <TableCell>{plan.active_subscription_count}</TableCell>
                <TableCell>
                  <Button
                    size="sm"
                    type="button"
                    variant={plan.is_public ? "secondary" : "outline"}
                    onClick={() => toggle(plan, "is_public")}
                  >
                    {boolText(plan.is_public)}
                  </Button>
                </TableCell>
                <TableCell>
                  <Button
                    size="sm"
                    type="button"
                    variant={plan.is_active ? "secondary" : "outline"}
                    onClick={() => toggle(plan, "is_active")}
                  >
                    {boolText(plan.is_active)}
                  </Button>
                </TableCell>
                <TableCell>
                  <div className="flex justify-end gap-2">
                    <Button asChild size="icon" variant="ghost" title="Edit plan">
                      <Link href={`/admin/plans/${plan.slug}/edit`}>
                        <Edit3 className="h-4 w-4" />
                      </Link>
                    </Button>
                    <Button asChild size="icon" variant="ghost" title="Version history">
                      <Link href={`/admin/plans/${plan.slug}/history`}>
                        <History className="h-4 w-4" />
                      </Link>
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {updateMetadata.isPending ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Updating plan
        </div>
      ) : null}
      {plans.length === 0 ? (
        <div className="rounded-md border p-6 text-sm text-muted-foreground">
          No plans exist yet.
        </div>
      ) : null}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-5xl">
          <DialogHeader>
            <DialogTitle>Create new plan</DialogTitle>
            <DialogDescription>
              Create the catalogue row and publish the first immutable version.
            </DialogDescription>
          </DialogHeader>
          <PlanEditForm mode="create" onFinished={() => setCreateOpen(false)} />
        </DialogContent>
      </Dialog>
    </div>
  );
}
