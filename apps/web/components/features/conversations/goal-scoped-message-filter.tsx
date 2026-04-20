"use client";

import { useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Filter, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { useGoalLifecycle } from "@/lib/hooks/use-goal-lifecycle";

interface GoalScopedMessageFilterProps {
  workspaceId: string;
  activeGoalId: string | null;
}

export function GoalScopedMessageFilter({
  workspaceId,
  activeGoalId,
}: GoalScopedMessageFilterProps) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { goals } = useGoalLifecycle(workspaceId);

  const isGoalScoped = searchParams.get("goal-scoped") === "true";
  const activeGoal = useMemo(
    () => goals.find((goal) => goal.id === activeGoalId) ?? null,
    [activeGoalId, goals],
  );

  function updateGoalScoped(nextValue: boolean) {
    const nextParams = new URLSearchParams(searchParams.toString());
    if (nextValue) {
      nextParams.set("goal-scoped", "true");
    } else {
      nextParams.delete("goal-scoped");
    }

    const nextQuery = nextParams.toString();
    router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname);
  }

  return (
    <Card className="border-border/70 bg-card/80">
      <CardContent className="space-y-4 p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Filter className="h-4 w-4 text-brand-accent" />
              Goal-scoped
            </div>
            <p className="text-sm text-muted-foreground">
              Limit the transcript to the messages already linked to the active
              workspace goal.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
              {isGoalScoped ? "On" : "Off"}
            </span>
            <Switch
              aria-label="Toggle goal-scoped filter"
              checked={isGoalScoped}
              disabled={!activeGoalId}
              onCheckedChange={updateGoalScoped}
            />
          </div>
        </div>
        {isGoalScoped && activeGoal ? (
          <div className="flex flex-col gap-3 rounded-2xl border border-brand-accent/30 bg-brand-accent/5 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="space-y-1">
              <p className="text-sm font-semibold text-foreground">
                Filtered to goal: {activeGoal.title}
              </p>
              <p className="text-sm text-muted-foreground">
                Showing the messages associated with this goal only.
              </p>
            </div>
            <Button
              onClick={() => updateGoalScoped(false)}
              size="sm"
              variant="ghost"
            >
              <X className="h-4 w-4" />
              Dismiss
            </Button>
          </div>
        ) : null}
        {!activeGoalId ? (
          <p className="text-sm text-muted-foreground">
            No active goal is available for this workspace yet.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
