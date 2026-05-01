"use client";

import { type ColumnDef } from "@tanstack/react-table";
import { Pencil, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { DataTable } from "@/components/shared/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useDeleteStatusSubscription,
  useUpdateStatusSubscription,
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
  const [editing, setEditing] = useState<StatusSubscription | null>(null);
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
        <div className="flex justify-end gap-1">
          <Button
            aria-label={`Edit ${row.original.channel} subscription`}
            size="icon"
            variant="ghost"
            onClick={() => setEditing(row.original)}
          >
            <Pencil className="h-4 w-4" />
          </Button>
          <Button
            aria-label={`Remove ${row.original.channel} subscription`}
            size="icon"
            variant="ghost"
            onClick={() => {
              if (window.confirm("Remove this status subscription?")) {
                void deleteSubscription.mutateAsync(row.original.id).catch(() => undefined);
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
    <>
      <DataTable
        columns={columns}
        data={subscriptions}
        emptyStateMessage="No status subscriptions configured."
        enableFiltering={false}
        isLoading={isLoading}
      />
      <EditSubscriptionDialog
        subscription={editing}
        onOpenChange={(open) => {
          if (!open) {
            setEditing(null);
          }
        }}
      />
    </>
  );
}

function EditSubscriptionDialog({
  subscription,
  onOpenChange,
}: {
  subscription: StatusSubscription | null;
  onOpenChange: (open: boolean) => void;
}) {
  const [target, setTarget] = useState("");
  const [scope, setScope] = useState("");
  const updateSubscription = useUpdateStatusSubscription(subscription?.id ?? "");

  useEffect(() => {
    setTarget(subscription?.target ?? "");
    setScope(subscription?.scope_components.join(", ") ?? "");
  }, [subscription]);

  const save = async () => {
    if (!subscription) {
      return;
    }
    await updateSubscription.mutateAsync({
      target: target.trim(),
      scope_components: parseScope(scope),
    });
    onOpenChange(false);
  };

  return (
    <Dialog open={subscription !== null} onOpenChange={onOpenChange}>
      <DialogContent aria-label="Edit status subscription">
        <DialogHeader>
          <DialogTitle>Edit status subscription</DialogTitle>
          <DialogDescription>Update the delivery target or component scope.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="status-subscription-target">Target</Label>
            <Input
              id="status-subscription-target"
              value={target}
              onChange={(event) => setTarget(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="status-subscription-scope">Component scope</Label>
            <Input
              id="status-subscription-scope"
              placeholder="control-plane-api, reasoning-engine"
              value={scope}
              onChange={(event) => setScope(event.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button
            disabled={updateSubscription.isPending}
            onClick={() => {
              void save();
            }}
          >
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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

function parseScope(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}
