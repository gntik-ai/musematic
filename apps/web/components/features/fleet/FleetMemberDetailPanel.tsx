"use client";

import { format } from "date-fns";
import { Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { FleetHealthGauge } from "@/components/features/fleet/FleetHealthGauge";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { useFleetMembers, useRemoveFleetMember, useUpdateMemberRole } from "@/lib/hooks/use-fleet-members";
import type { FleetMemberRole } from "@/lib/types/fleet";

interface FleetMemberDetailPanelProps {
  fleetId: string;
  memberId: string;
  onClose: () => void;
}

export function FleetMemberDetailPanel({
  fleetId,
  memberId,
  onClose,
}: FleetMemberDetailPanelProps) {
  const membersQuery = useFleetMembers(fleetId);
  const removeMemberMutation = useRemoveFleetMember();
  const updateRoleMutation = useUpdateMemberRole();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const member = useMemo(
    () => membersQuery.data?.find((entry) => entry.id === memberId) ?? null,
    [memberId, membersQuery.data],
  );

  if (!member) {
    return null;
  }

  return (
    <>
      <Sheet open onOpenChange={(open) => (!open ? onClose() : undefined)}>
        <SheetContent className="ml-auto flex h-full max-w-md flex-col overflow-y-auto rounded-none border-l border-border p-6">
          <div className="space-y-6">
            <div className="space-y-2">
              <p className="text-sm font-medium text-muted-foreground">Fleet member</p>
              <div>
                <h2 className="text-2xl font-semibold">{member.agent_name}</h2>
                <p className="text-sm text-muted-foreground">{member.agent_fqn}</p>
              </div>
            </div>

            <div className="rounded-3xl border border-border/60 bg-card/70 p-5">
              <FleetHealthGauge fleetId={fleetId} showBreakdown={false} size="sm" />
            </div>

            <dl className="grid gap-4 rounded-3xl border border-border/60 bg-card/70 p-5 text-sm">
              <div className="flex items-center justify-between gap-3">
                <dt className="text-muted-foreground">Role</dt>
                <dd className="font-medium capitalize">{member.role}</dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt className="text-muted-foreground">Availability</dt>
                <dd className="font-medium capitalize">{member.availability}</dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt className="text-muted-foreground">Joined</dt>
                <dd className="font-medium">{format(new Date(member.joined_at), "PPp")}</dd>
              </div>
              <div className="space-y-1">
                <dt className="text-muted-foreground">Last error</dt>
                <dd title={member.last_error ?? "No recent errors"} className="text-sm">
                  {member.last_error ?? "No recent errors"}
                </dd>
              </div>
            </dl>

            <div className="space-y-2">
              <label className="block text-sm font-medium" htmlFor="member-role">
                Change role
              </label>
              <Select
                defaultValue={member.role}
                id="member-role"
                onChange={(event) => {
                  const nextRole = event.target.value as FleetMemberRole;
                  if (nextRole === member.role) {
                    return;
                  }

                  void updateRoleMutation.mutateAsync({
                    fleetId,
                    memberId: member.id,
                    role: nextRole,
                  });
                }}
              >
                <option value="lead">Lead</option>
                <option value="worker">Worker</option>
                <option value="observer">Observer</option>
              </Select>
            </div>

            <Button
              aria-label="Remove member"
              className="gap-2"
              variant="destructive"
              onClick={() => setConfirmOpen(true)}
            >
              <Trash2 className="h-4 w-4" />
              Remove member
            </Button>
          </div>
        </SheetContent>
      </Sheet>

      <ConfirmDialog
        confirmLabel="Remove member"
        description={`Remove ${member.agent_name} from the fleet?`}
        isLoading={removeMemberMutation.isPending}
        open={confirmOpen}
        title="Confirm removal"
        variant="destructive"
        onConfirm={() => {
          void removeMemberMutation.mutateAsync({
            fleetId,
            memberId: member.id,
          }).then(() => {
            setConfirmOpen(false);
            onClose();
          });
        }}
        onOpenChange={setConfirmOpen}
      />
    </>
  );
}

