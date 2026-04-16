"use client";

import { useMemo, useState } from "react";
import { format } from "date-fns";
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
import { Checkbox } from "@/components/ui/checkbox";
import { AgentStatusBadge } from "@/components/features/agent-management/AgentStatusBadge";
import { useRollbackRevision } from "@/lib/hooks/use-agent-mutations";
import { useAgentRevisions } from "@/lib/hooks/use-agent-revisions";
import { useToast } from "@/lib/hooks/use-toast";
import { ApiError } from "@/types/api";

export interface AgentRevisionTimelineProps {
  fqn: string;
  onSelectForDiff?: (revisions: [number, number]) => void;
  onRollback?: (revisionNumber: number) => void;
}

export function AgentRevisionTimeline({
  fqn,
  onSelectForDiff,
  onRollback,
}: AgentRevisionTimelineProps) {
  const revisionsQuery = useAgentRevisions(fqn);
  const rollbackMutation = useRollbackRevision();
  const { toast } = useToast();
  const [selectedRevisions, setSelectedRevisions] = useState<number[]>([]);
  const [rollbackTarget, setRollbackTarget] = useState<number | null>(null);

  const revisions = useMemo(
    () => revisionsQuery.data?.items ?? [],
    [revisionsQuery.data],
  );

  const toggleRevision = (revisionNumber: number) => {
    setSelectedRevisions((current) => {
      if (current.includes(revisionNumber)) {
        return current.filter((entry) => entry !== revisionNumber);
      }

      if (current.length >= 2) {
        return current;
      }

      return [...current, revisionNumber].sort((left, right) => left - right);
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 rounded-2xl border border-border/60 bg-card/80 p-4">
        <div>
          <h2 className="font-semibold">Revision timeline</h2>
          <p className="text-sm text-muted-foreground">
            Select exactly two revisions to compare.
          </p>
        </div>
        <Button
          disabled={selectedRevisions.length !== 2}
          onClick={() => {
            if (selectedRevisions.length === 2) {
              const [baseRevision, compareRevision] = selectedRevisions;
              if (baseRevision !== undefined && compareRevision !== undefined) {
                onSelectForDiff?.([baseRevision, compareRevision]);
              }
            }
          }}
        >
          Compare selected
        </Button>
      </div>

      <ol className="space-y-3">
        {revisions.map((revision) => {
          const checked = selectedRevisions.includes(revision.revision_number);
          const disableUnchecked = !checked && selectedRevisions.length >= 2;

          return (
            <li
              key={revision.revision_id}
              className="rounded-2xl border border-border/60 bg-card/80 p-4"
            >
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="flex items-start gap-3">
                  <Checkbox
                    aria-label={`Select revision ${revision.revision_number}`}
                    checked={checked}
                    disabled={disableUnchecked}
                    onChange={() => toggleRevision(revision.revision_number)}
                  />
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium">Revision {revision.revision_number}</p>
                      <AgentStatusBadge status={revision.status} />
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {format(new Date(revision.created_at), "MMM d, yyyy HH:mm")} by{" "}
                      {revision.created_by}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {revision.change_summary}
                    </p>
                  </div>
                </div>
                <Button
                  size="sm"
                  type="button"
                  variant="outline"
                  onClick={() => setRollbackTarget(revision.revision_number)}
                >
                  Rollback
                </Button>
              </div>
            </li>
          );
        })}
      </ol>

      <AlertDialog
        open={rollbackTarget !== null}
        onOpenChange={(open) => {
          if (!open) {
            setRollbackTarget(null);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Rollback revision?</AlertDialogTitle>
            <AlertDialogDescription>
              This will create a new revision cloned from revision {rollbackTarget}.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="rounded-md border border-border px-4 py-2 text-sm">
              Cancel
            </AlertDialogCancel>
            <Button
              disabled={rollbackMutation.isPending || rollbackTarget === null}
              onClick={async () => {
                if (rollbackTarget === null) {
                  return;
                }

                try {
                  await rollbackMutation.mutateAsync({
                    fqn,
                    revisionNumber: rollbackTarget,
                  });
                  toast({
                    title: "Revision restored",
                    variant: "success",
                  });
                  onRollback?.(rollbackTarget);
                  setRollbackTarget(null);
                } catch (error) {
                  toast({
                    title: error instanceof ApiError ? error.message : "Rollback failed",
                    variant: "destructive",
                  });
                }
              }}
            >
              {rollbackMutation.isPending ? "Rolling back…" : "Confirm rollback"}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
