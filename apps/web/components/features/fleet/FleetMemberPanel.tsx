"use client";

import { format } from "date-fns";
import { Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { AddMemberDialog } from "@/components/features/fleet/AddMemberDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useFleetMembers, useRemoveFleetMember } from "@/lib/hooks/use-fleet-members";
import { getFleetHealthTone } from "@/lib/types/fleet";
import { ApiError } from "@/types/api";

interface FleetMemberPanelProps {
  fleetId: string;
}

export function FleetMemberPanel({ fleetId }: FleetMemberPanelProps) {
  const membersQuery = useFleetMembers(fleetId);
  const removeMemberMutation = useRemoveFleetMember();
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [memberToRemove, setMemberToRemove] = useState<string | null>(null);
  const members = membersQuery.data ?? [];
  const selectedMember = useMemo(
    () => members.find((member) => member.id === memberToRemove) ?? null,
    [memberToRemove, members],
  );
  const removeError =
    removeMemberMutation.error instanceof ApiError &&
    removeMemberMutation.error.status === 409
      ? removeMemberMutation.error
      : null;

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-xl font-semibold">Members</h3>
          <p className="text-sm text-muted-foreground">
            Inspect individual health, roles, and availability across the fleet.
          </p>
        </div>
        <Button className="gap-2" onClick={() => setAddDialogOpen(true)}>
          <Plus className="h-4 w-4" />
          Add member
        </Button>
      </div>

      <div className="grid gap-3">
        {members.map((member) => {
          const tone = getFleetHealthTone(member.health_pct);
          const dotClassName =
            tone === "healthy"
              ? "bg-emerald-500"
              : tone === "warning"
                ? "bg-amber-500"
                : "bg-rose-500";

          return (
            <article
              key={member.id}
              className={`rounded-[1.6rem] border bg-card/80 p-5 shadow-sm ${
                member.status === "errored"
                  ? "border-rose-400/70 bg-rose-500/5"
                  : "border-border/60"
              }`}
            >
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="text-lg font-semibold">{member.agent_name}</h4>
                    <Badge className="capitalize" variant="outline">
                      {member.role}
                    </Badge>
                    <span className={`h-2.5 w-2.5 rounded-full ${dotClassName}`} />
                  </div>
                  <p className="text-sm text-muted-foreground">{member.agent_fqn}</p>
                  <div className="flex flex-wrap items-center gap-4 text-sm">
                    <span className="capitalize">{member.availability}</span>
                    <span className="capitalize">{member.status}</span>
                    <span>{member.health_pct}% health</span>
                    <span>Joined {format(new Date(member.joined_at), "PP")}</span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {member.last_error ? (
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger>
                          <span
                            className="rounded-full border border-rose-300 bg-rose-50 px-3 py-1 text-xs font-medium text-rose-900 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-100"
                            title={member.last_error}
                          >
                            Error surfaced
                          </span>
                        </TooltipTrigger>
                        <TooltipContent>{member.last_error}</TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  ) : null}
                  <Button
                    aria-label={`Remove ${member.agent_name}`}
                    className="gap-2"
                    variant="outline"
                    onClick={() => {
                      removeMemberMutation.reset();
                      setMemberToRemove(member.id);
                    }}
                  >
                    <Trash2 className="h-4 w-4" />
                    Remove
                  </Button>
                </div>
              </div>
            </article>
          );
        })}
      </div>

      <AddMemberDialog
        fleetId={fleetId}
        open={addDialogOpen}
        onMemberAdded={() => setAddDialogOpen(false)}
        onOpenChange={setAddDialogOpen}
      />

      <ConfirmDialog
        confirmLabel={removeError ? "Retry removal" : "Remove member"}
        description={
          removeError
            ? `${removeError.message}${removeError.meta?.active_executions ? ` Active executions: ${removeError.meta.active_executions}.` : ""}`
            : selectedMember
              ? `Remove ${selectedMember.agent_name} from this fleet?`
              : "Remove this member?"
        }
        isLoading={removeMemberMutation.isPending}
        open={Boolean(selectedMember)}
        title={removeError ? "Removal blocked" : "Confirm removal"}
        variant="destructive"
        onConfirm={() => {
          if (!selectedMember) {
            return;
          }

          void removeMemberMutation
            .mutateAsync({ fleetId, memberId: selectedMember.id })
            .then(() => {
              setMemberToRemove(null);
            });
        }}
        onOpenChange={(open) => {
          if (!open) {
            setMemberToRemove(null);
          }
        }}
      />
    </div>
  );
}

