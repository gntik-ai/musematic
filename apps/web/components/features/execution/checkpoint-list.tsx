"use client";

import { useMemo, useState } from "react";
import { RotateCcw } from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useExecutionCheckpoints, useCheckpointRollback } from "@/lib/hooks/use-execution-checkpoints";
import { useAuthStore } from "@/store/auth-store";
import type { Checkpoint } from "@/types/trajectory";

export interface CheckpointListProps {
  executionId: string;
}

const ADMIN_ROLES = new Set(["workspace_admin", "platform_admin", "superadmin"]);

function canRollbackForRoles(roles: string[] | undefined): boolean {
  return (roles ?? []).some((role) => ADMIN_ROLES.has(role));
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Date unavailable";
  }
  return date.toLocaleString();
}

export function CheckpointList({ executionId }: CheckpointListProps) {
  const checkpointsQuery = useExecutionCheckpoints(executionId);
  const rollbackMutation = useCheckpointRollback(executionId);
  const roles = useAuthStore((state) => state.user?.roles);
  const canRollback = useMemo(() => canRollbackForRoles(roles), [roles]);
  const [selectedCheckpoint, setSelectedCheckpoint] = useState<Checkpoint | null>(null);

  const confirmDialogProps = selectedCheckpoint
    ? {
        description: `Type ${selectedCheckpoint.id} to confirm rollback to checkpoint #${selectedCheckpoint.stepIndex}.`,
        requireTypedConfirmation: selectedCheckpoint.id,
        title: `Roll back to checkpoint #${selectedCheckpoint.stepIndex}`,
      }
    : {
        description: "",
        title: "Roll back",
      };

  const confirmRollback = async () => {
    if (!selectedCheckpoint) {
      return;
    }

    await rollbackMutation.mutateAsync({
      checkpointNumber: selectedCheckpoint.stepIndex,
    });
    setSelectedCheckpoint(null);
  };

  return (
    <>
      <Card className="rounded-[1.75rem]">
        <CardHeader>
          <CardTitle>Checkpoints</CardTitle>
          <p className="text-sm text-muted-foreground">
            Recovery points captured for this execution. Rolling back replays from the selected checkpoint.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          {!canRollback ? (
            <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-800">
              Rolling back checkpoints requires the workspace_admin role.
            </div>
          ) : null}
          {checkpointsQuery.isLoading ? (
            Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-28 rounded-2xl" />
            ))
          ) : checkpointsQuery.data.length === 0 ? (
            <EmptyState
              description="No checkpoints were recorded for this execution."
              title="Checkpoint history unavailable"
            />
          ) : (
            <div className="space-y-3">
              {checkpointsQuery.data.map((checkpoint) => (
                <div
                  key={checkpoint.id}
                  className="rounded-2xl border border-border/60 bg-background/80 p-4 shadow-sm"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="outline">Checkpoint #{checkpoint.stepIndex}</Badge>
                        {checkpoint.isRollbackCandidate ? (
                          <Badge className="border-emerald-500/30 bg-emerald-500/10 text-emerald-700" variant="outline">
                            Rollback candidate
                          </Badge>
                        ) : (
                          <Badge className="border-border/70 bg-muted/60 text-muted-foreground" variant="outline">
                            Superseded
                          </Badge>
                        )}
                      </div>
                      <p className="font-mono text-sm text-muted-foreground">{checkpoint.id}</p>
                    </div>
                    <Button
                      disabled={!canRollback || !checkpoint.isRollbackCandidate || rollbackMutation.isPending}
                      onClick={() => setSelectedCheckpoint(checkpoint)}
                      variant="outline"
                    >
                      <RotateCcw className="h-4 w-4" />
                      Roll back
                    </Button>
                  </div>
                  <p className="mt-3 text-sm text-muted-foreground">{checkpoint.reason}</p>
                  <p className="mt-2 text-xs text-muted-foreground">Created {formatDate(checkpoint.createdAt)}</p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
      <ConfirmDialog
        cancelLabel="Keep running"
        confirmLabel="Roll back"
        isLoading={rollbackMutation.isPending}
        onConfirm={() => {
          void confirmRollback();
        }}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedCheckpoint(null);
          }
        }}
        open={selectedCheckpoint !== null}
        variant="destructive"
        {...confirmDialogProps}
      />
    </>
  );
}
