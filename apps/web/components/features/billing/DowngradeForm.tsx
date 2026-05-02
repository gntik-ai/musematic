"use client";

import { useState } from "react";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useDowngradeSubscription } from "@/lib/hooks/use-plan-mutations";
import { useWorkspaceBilling } from "@/lib/hooks/use-workspace-billing";

export function DowngradeForm({ workspaceId }: { workspaceId: string }) {
  const billing = useWorkspaceBilling(workspaceId);
  const downgrade = useDowngradeSubscription(workspaceId);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const usage = billing.data?.usage;
  const agentsAboveFree = Math.max((usage?.active_agents_in_this_workspace ?? 0) - 5, 0);
  const usersAboveFree = Math.max((usage?.active_users_in_this_workspace ?? 0) - 3, 0);
  const workspacesAboveFree = Math.max((usage?.active_workspaces ?? 0) - 1, 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Schedule downgrade</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 text-sm sm:grid-cols-3">
          <div>
            <div className="text-muted-foreground">Agents above Free</div>
            <div className="font-medium">{agentsAboveFree}</div>
          </div>
          <div>
            <div className="text-muted-foreground">Users above Free</div>
            <div className="font-medium">{usersAboveFree}</div>
          </div>
          <div>
            <div className="text-muted-foreground">Effective</div>
            <div className="font-medium">
              {billing.data?.subscription.current_period_end
                ? new Date(billing.data.subscription.current_period_end).toLocaleDateString()
                : "Period end"}
            </div>
          </div>
        </div>
        <Button
          variant="destructive"
          disabled={downgrade.isPending}
          onClick={() => setConfirmOpen(true)}
        >
          Schedule downgrade
        </Button>
        <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Confirm downgrade</AlertDialogTitle>
              <AlertDialogDescription>
                {workspacesAboveFree} workspaces, {agentsAboveFree} agents, and {usersAboveFree}{" "}
                users are above Free limits. Existing data stays in place.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <Button type="button" variant="outline" onClick={() => setConfirmOpen(false)}>
                Cancel
              </Button>
              <Button
                type="button"
                variant="destructive"
                disabled={downgrade.isPending}
                onClick={() => {
                  downgrade.mutate({ workspaceId, target_plan_slug: "free" });
                  setConfirmOpen(false);
                }}
              >
                Schedule downgrade
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </CardContent>
    </Card>
  );
}
