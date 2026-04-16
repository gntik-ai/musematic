"use client";

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import type { PublicationSummary } from "@/lib/types/agent-management";

export interface PublicationConfirmDialogProps {
  open: boolean;
  summary: PublicationSummary | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export function PublicationConfirmDialog({
  open,
  summary,
  onConfirm,
  onCancel,
}: PublicationConfirmDialogProps) {
  return (
    <AlertDialog open={open} onOpenChange={(nextOpen) => !nextOpen && onCancel()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Publish agent?</AlertDialogTitle>
          <AlertDialogDescription>
            Review the impact before moving this agent into the active lifecycle.
          </AlertDialogDescription>
        </AlertDialogHeader>
        {summary ? (
          <div className="space-y-3 rounded-xl border border-border/60 bg-background/70 p-4 text-sm">
            <p>
              <span className="font-medium">FQN:</span> {summary.fqn}
            </p>
            <p>
              <span className="font-medium">Status:</span> {summary.previous_status} →{" "}
              {summary.new_status}
            </p>
            <p>
              <span className="font-medium">Affected workspaces:</span>{" "}
              {summary.affected_workspaces.join(", ")}
            </p>
            <p>
              <span className="font-medium">Published at:</span> {summary.published_at}
            </p>
          </div>
        ) : null}
        <AlertDialogFooter>
          <AlertDialogCancel className="rounded-md border border-border px-4 py-2 text-sm">
            Cancel
          </AlertDialogCancel>
          <Button onClick={onConfirm}>Confirm publish</Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
