"use client";

import { useMemo, useState } from "react";
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
import { Progress } from "@/components/ui/progress";
import { useAgents } from "@/lib/hooks/use-agents";
import { useAddFleetMember } from "@/lib/hooks/use-fleet-members";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

interface ScaleDialogProps {
  fleetId: string;
  currentMemberCount: number;
  existingMemberFqns?: string[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ScaleDialog({
  fleetId,
  currentMemberCount,
  existingMemberFqns = [],
  open,
  onOpenChange,
}: ScaleDialogProps) {
  const [targetCount, setTargetCount] = useState(currentMemberCount);
  const [completed, setCompleted] = useState(0);
  const [isRunning, setIsRunning] = useState(false);
  const currentWorkspaceId = useWorkspaceStore(
    (state) => state.currentWorkspace?.id ?? null,
  );
  const authWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspaceId ?? authWorkspaceId;
  const agentsQuery = useAgents(
    {
      status: ["active"],
      limit: 50,
      sort_by: "updated_at",
      sort_order: "desc",
    },
    {
      enabled: open && Boolean(workspaceId),
      workspaceId,
    },
  );
  const addMemberMutation = useAddFleetMember();

  const additionalCount = Math.max(0, targetCount - currentMemberCount);
  const previewAgents = useMemo(
    () =>
      agentsQuery.agents
        .filter((agent) => !existingMemberFqns.includes(agent.fqn))
        .slice(0, additionalCount),
    [additionalCount, agentsQuery.agents, existingMemberFqns],
  );

  const progressValue =
    additionalCount === 0 ? 0 : Math.round((completed / additionalCount) * 100);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl space-y-5">
        <DialogHeader>
          <DialogTitle>Scale fleet</DialogTitle>
          <DialogDescription>
            Increase the member count by adding compatible registry agents in sequence.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          <label className="block text-sm font-medium" htmlFor="target-member-count">
            Target member count
          </label>
          <Input
            id="target-member-count"
            min={currentMemberCount}
            type="number"
            value={targetCount}
            onChange={(event) =>
              setTargetCount(Math.max(currentMemberCount, Number(event.target.value) || currentMemberCount))
            }
          />
        </div>

        <div className="space-y-3 rounded-3xl border border-border/60 bg-card/70 p-4">
          <div className="flex items-center justify-between gap-3">
            <p className="font-medium">Preview additions</p>
            <p className="text-sm text-muted-foreground">
              {previewAgents.length} of {additionalCount} available
            </p>
          </div>
          <div className="grid gap-2">
            {previewAgents.map((agent) => (
              <div key={agent.fqn} className="rounded-2xl border border-border/60 bg-background/70 px-4 py-3">
                <p className="font-medium">{agent.name}</p>
                <p className="text-sm text-muted-foreground">{agent.fqn}</p>
              </div>
            ))}
            {additionalCount === 0 ? (
              <p className="text-sm text-muted-foreground">Target already matches the current member count.</p>
            ) : null}
          </div>
          {isRunning ? (
            <div className="space-y-2">
              <Progress value={progressValue} />
              <p className="text-sm text-muted-foreground">
                Added {completed} of {additionalCount} requested members.
              </p>
            </div>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={isRunning || additionalCount === 0 || previewAgents.length === 0}
            onClick={() => {
              void (async () => {
                setCompleted(0);
                setIsRunning(true);
                for (const agent of previewAgents) {
                  await addMemberMutation.mutateAsync({
                    fleetId,
                    agentFqn: agent.fqn,
                    role: "worker",
                  });
                  setCompleted((current) => current + 1);
                }
                setIsRunning(false);
                onOpenChange(false);
              })();
            }}
          >
            Confirm scale
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

