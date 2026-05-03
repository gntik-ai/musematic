"use client";

/**
 * UPD-050 — Suspension detail with lift action.
 *
 * Shows full evidence_json + reason + actor trail. Lift opens a Dialog
 * that requires a non-empty reason.
 */

import { useState } from "react";
import { useLiftSuspension, useSuspensionDetail } from "@/lib/hooks/use-suspensions";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

interface SuspensionDetailProps {
  suspensionId: string;
}

export function SuspensionDetail({ suspensionId }: SuspensionDetailProps) {
  const { data, isLoading, isError } = useSuspensionDetail(suspensionId);
  const lift = useLiftSuspension();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");

  if (isLoading) {
    return <Skeleton className="h-64 w-full" />;
  }
  if (isError || !data) {
    return (
      <div className="rounded-md border p-8 text-center text-muted-foreground">
        Suspension not found.
      </div>
    );
  }

  const isLifted = data.lifted_at !== null;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="space-y-1">
          <div className="flex items-center justify-between">
            <CardTitle className="font-mono text-lg">
              user {data.user_id}
            </CardTitle>
            {isLifted ? <Badge variant="outline">Lifted</Badge> : <Badge>Active</Badge>}
          </div>
          <p className="text-sm text-muted-foreground">
            Suspended {data.suspended_at} by {data.suspended_by}
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <section>
            <h3 className="text-sm font-medium">Reason</h3>
            <Badge variant="secondary" className="mt-1">
              {data.reason}
            </Badge>
          </section>
          <section>
            <h3 className="text-sm font-medium">Evidence</h3>
            <pre className="mt-1 max-h-72 overflow-auto rounded-md bg-muted p-3 text-xs">
              {JSON.stringify(data.evidence_json, null, 2)}
            </pre>
          </section>
          {isLifted ? (
            <section>
              <h3 className="text-sm font-medium">Lift trail</h3>
              <p className="mt-1 text-sm">
                Lifted at {data.lifted_at} by user {data.lifted_by_user_id}
              </p>
              {data.lift_reason ? (
                <p className="mt-1 whitespace-pre-wrap text-sm text-muted-foreground">
                  {data.lift_reason}
                </p>
              ) : null}
            </section>
          ) : null}
        </CardContent>
      </Card>

      {!isLifted ? (
        <Button onClick={() => setOpen(true)} variant="default">
          Lift suspension…
        </Button>
      ) : null}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Lift suspension</DialogTitle>
            <DialogDescription>
              The user receives a notification that their account is reinstated.
              The reason is required and recorded in the audit chain.
            </DialogDescription>
          </DialogHeader>
          <Textarea
            rows={4}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Explain why this suspension is being lifted (e.g., 'Reviewed evidence; user is legitimate')."
          />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="default"
              disabled={!reason.trim() || lift.isPending}
              onClick={async () => {
                await lift.mutateAsync({
                  id: suspensionId,
                  body: { reason: reason.trim() },
                });
                setOpen(false);
                setReason("");
              }}
            >
              Lift
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
