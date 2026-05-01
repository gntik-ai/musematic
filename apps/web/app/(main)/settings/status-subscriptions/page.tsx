"use client";

import { useState } from "react";
import { BellPlus } from "lucide-react";
import { AddSubscriptionForm } from "@/components/features/platform-status/AddSubscriptionForm";
import { StatusSubscriptionList } from "@/components/features/platform-status/StatusSubscriptionList";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useStatusSubscriptions } from "@/lib/hooks/use-status-subscriptions";

export default function StatusSubscriptionsSettingsPage() {
  const subscriptionsQuery = useStatusSubscriptions();
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <section className="mx-auto w-full max-w-6xl space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Status subscriptions</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Manage email, webhook, and Slack status notifications for your account.
          </p>
        </div>
        <Button onClick={() => setDialogOpen(true)}>
          <BellPlus className="h-4 w-4" />
          Add Subscription
        </Button>
      </div>
      <StatusSubscriptionList
        isLoading={subscriptionsQuery.isLoading}
        subscriptions={subscriptionsQuery.data?.items ?? []}
      />
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add status subscription</DialogTitle>
            <DialogDescription>
              Choose a channel and optional component scope.
            </DialogDescription>
          </DialogHeader>
          <AddSubscriptionForm onCreated={() => setDialogOpen(false)} />
        </DialogContent>
      </Dialog>
    </section>
  );
}
