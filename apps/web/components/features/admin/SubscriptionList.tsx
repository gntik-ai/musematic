"use client";

import Link from "next/link";
import { Eye } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAdminSubscriptions } from "@/lib/hooks/use-admin-subscriptions";
import { SubscriptionStatusBadge } from "./SubscriptionStatusBadge";

export function SubscriptionList() {
  const subscriptions = useAdminSubscriptions();

  if (subscriptions.isLoading) {
    return <Skeleton className="h-80 w-full" />;
  }

  const items = subscriptions.data?.items ?? [];

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Tenant</TableHead>
            <TableHead>Scope</TableHead>
            <TableHead>Plan</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Current period end</TableHead>
            <TableHead>Payment</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((subscription) => (
            <TableRow key={subscription.id}>
              <TableCell>
                <div className="font-medium">{subscription.tenant_slug ?? "unknown"}</div>
                <div className="text-xs text-muted-foreground">{subscription.tenant_id}</div>
              </TableCell>
              <TableCell>
                <div>{subscription.scope_type}</div>
                <div className="text-xs text-muted-foreground">{subscription.scope_id}</div>
              </TableCell>
              <TableCell>
                {subscription.plan_slug} v{subscription.plan_version}
              </TableCell>
              <TableCell>
                <SubscriptionStatusBadge status={subscription.status} />
              </TableCell>
              <TableCell>
                {new Date(subscription.current_period_end).toLocaleString()}
              </TableCell>
              <TableCell>{subscription.stripe_subscription_id ? "provider" : "stub"}</TableCell>
              <TableCell>
                <div className="flex justify-end">
                  <Button asChild size="icon" variant="ghost" title="View subscription">
                    <Link href={`/admin/subscriptions/${subscription.id}`}>
                      <Eye className="h-4 w-4" />
                    </Link>
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {items.length === 0 ? (
        <div className="p-6 text-sm text-muted-foreground">No subscriptions found.</div>
      ) : null}
    </div>
  );
}
