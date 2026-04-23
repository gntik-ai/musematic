"use client";

import { useState } from "react";
import { Flag } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import {
  useGoalLifecycle,
  useGoalLifecycleMutations,
} from "@/lib/hooks/use-goal-lifecycle";

const stateVariant: Record<string, string> = {
  open: "bg-slate-500/15 text-slate-700",
  in_progress: "bg-sky-500/15 text-sky-700",
  completed: "bg-emerald-500/15 text-emerald-700",
  cancelled: "bg-rose-500/15 text-rose-700",
};

interface WorkspaceGoalHeaderProps {
  workspaceId: string;
}

export function WorkspaceGoalHeader({ workspaceId }: WorkspaceGoalHeaderProps) {
  const { activeGoal, isLoading } = useGoalLifecycle(workspaceId);
  const mutation = useGoalLifecycleMutations(workspaceId);
  const [confirmOpen, setConfirmOpen] = useState(false);

  if (isLoading || !activeGoal) {
    return null;
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm font-semibold text-brand-accent">
            <Flag className="h-4 w-4" />
            Active goal
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-semibold">{activeGoal.title}</h3>
            <Badge className={stateVariant[activeGoal.state] ?? ""} variant="outline">
              {activeGoal.state.replace("_", " ")}
            </Badge>
          </div>
          {activeGoal.description ? (
            <p className="text-sm text-muted-foreground">{activeGoal.description}</p>
          ) : null}
        </div>
        <Button
          disabled={
            mutation.isPending ||
            (activeGoal.state !== "open" && activeGoal.state !== "in_progress")
          }
          onClick={() => setConfirmOpen(true)}
        >
          Complete Goal
        </Button>
      </CardContent>
      <ConfirmDialog
        confirmLabel="Complete Goal"
        description={`Mark "${activeGoal.title}" as completed? This goal will stop accepting new active work.`}
        isLoading={mutation.isPending}
        onConfirm={() => {
          mutation.mutate(
            {
              goalId: activeGoal.id,
              state: "completed",
            },
            {
              onSuccess: () => setConfirmOpen(false),
            },
          );
        }}
        onOpenChange={setConfirmOpen}
        open={confirmOpen}
        title="Complete active goal"
      />
    </Card>
  );
}
