"use client";

import { type ColumnDef } from "@tanstack/react-table";
import { Trash2 } from "lucide-react";
import { DataTable } from "@/components/shared/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  useDeleteStatusSubscription,
  type StatusSubscription,
} from "@/lib/hooks/use-status-subscriptions";

export function StatusSubscriptionList({
  subscriptions,
  isLoading = false,
}: {
  subscriptions: StatusSubscription[];
  isLoading?: boolean;
}) {
  const deleteSubscription = useDeleteStatusSubscription();
  const columns: ColumnDef<StatusSubscription>[] = [
    {
      accessorKey: "channel",
      header: "Channel",
      cell: ({ row }) => channelLabel(row.original.channel),
    },
    {
      accessorKey: "target",
      header: "Target",
    },
    {
      id: "scope",
      header: "Scope",
      cell: ({ row }) =>
        row.original.scope_components.length
          ? row.original.scope_components.join(", ")
          : "All components",
    },
    {
      accessorKey: "health",
      header: "Health",
      cell: ({ row }) => (
        <Badge className={healthClass(row.original.health)} variant="secondary">
          {row.original.health}
        </Badge>
      ),
    },
    {
      id: "confirmed",
      header: "Confirmed",
      cell: ({ row }) =>
        row.original.confirmed_at
          ? new Date(row.original.confirmed_at).toLocaleString()
          : "Pending",
    },
    {
      id: "actions",
      header: "",
      cell: ({ row }) => (
        <div className="flex justify-end">
          <Button
            aria-label={`Remove ${row.original.channel} subscription`}
            size="icon"
            variant="ghost"
            onClick={() => {
              if (window.confirm("Remove this status subscription?")) {
                void deleteSubscription.mutateAsync(row.original.id);
              }
            }}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      ),
    },
  ];

  return (
    <DataTable
      columns={columns}
      data={subscriptions}
      emptyStateMessage="No status subscriptions configured."
      enableFiltering={false}
      isLoading={isLoading}
    />
  );
}

function channelLabel(channel: StatusSubscription["channel"]) {
  if (channel === "email") {
    return "Email";
  }
  if (channel === "slack") {
    return "Slack";
  }
  return "Webhook";
}

function healthClass(health: StatusSubscription["health"]) {
  switch (health) {
    case "healthy":
      return "bg-emerald-500/15 text-emerald-700";
    case "unhealthy":
      return "bg-destructive/10 text-foreground";
    case "unsubscribed":
      return "text-muted-foreground";
    case "pending":
    default:
      return "bg-amber-500/15 text-amber-700";
  }
}
