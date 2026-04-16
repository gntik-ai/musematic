"use client";

import { useMemo, useState } from "react";
import { SearchInput } from "@/components/shared/SearchInput";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import { useAgents } from "@/lib/hooks/use-agents";
import { useAddFleetMember } from "@/lib/hooks/use-fleet-members";
import type { FleetMemberRole } from "@/lib/types/fleet";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

interface AddMemberDialogProps {
  fleetId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onMemberAdded: () => void;
}

export function AddMemberDialog({
  fleetId,
  open,
  onOpenChange,
  onMemberAdded,
}: AddMemberDialogProps) {
  const [search, setSearch] = useState("");
  const [selectedAgentFqn, setSelectedAgentFqn] = useState<string | null>(null);
  const [role, setRole] = useState<FleetMemberRole>("worker");
  const currentWorkspaceId = useWorkspaceStore(
    (state) => state.currentWorkspace?.id ?? null,
  );
  const authWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspaceId ?? authWorkspaceId;
  const addMemberMutation = useAddFleetMember();
  const agentsQuery = useAgents(
    {
      search,
      status: ["active"],
      limit: 25,
    },
    {
      enabled: open && Boolean(workspaceId),
      workspaceId,
    },
  );

  const results = useMemo(
    () => agentsQuery.agents.slice(0, 8),
    [agentsQuery.agents],
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl space-y-5">
        <DialogHeader>
          <DialogTitle>Add member</DialogTitle>
          <DialogDescription>
            Search the registry, choose an agent, and assign its role in the fleet.
          </DialogDescription>
        </DialogHeader>

        <SearchInput
          defaultValue={search}
          isLoading={agentsQuery.isFetching}
          placeholder="Search agents"
          onChange={setSearch}
        />

        <div className="grid gap-3 rounded-3xl border border-border/60 bg-card/70 p-4">
          {results.map((agent) => (
            <button
              key={agent.fqn}
              className={`rounded-2xl border px-4 py-3 text-left ${
                selectedAgentFqn === agent.fqn
                  ? "border-primary bg-primary/5"
                  : "border-border/60 bg-background/70"
              }`}
              type="button"
              onClick={() => setSelectedAgentFqn(agent.fqn)}
            >
              <p className="font-medium">{agent.name}</p>
              <p className="text-sm text-muted-foreground">{agent.fqn}</p>
            </button>
          ))}
          {results.length === 0 ? (
            <p className="text-sm text-muted-foreground">No agents match the current search.</p>
          ) : null}
        </div>

        <div className="space-y-2">
          <label className="block text-sm font-medium" htmlFor="new-member-role">
            Role
          </label>
          <Select
            id="new-member-role"
            value={role}
            onChange={(event) => setRole(event.target.value as FleetMemberRole)}
          >
            <option value="lead">Lead</option>
            <option value="worker">Worker</option>
            <option value="observer">Observer</option>
          </Select>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={!selectedAgentFqn || addMemberMutation.isPending}
            onClick={() => {
              if (!selectedAgentFqn) {
                return;
              }

              void addMemberMutation.mutateAsync({
                fleetId,
                agentFqn: selectedAgentFqn,
                role,
              }).then(() => {
                setSelectedAgentFqn(null);
                setSearch("");
                onOpenChange(false);
                onMemberAdded();
              });
            }}
          >
            Add member
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

