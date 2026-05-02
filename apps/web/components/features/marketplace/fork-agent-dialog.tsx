"use client";

/**
 * UPD-049 — Fork dialog. Lets the consumer fork a public agent into
 * their own tenant or workspace, choosing a fresh local_name.
 */

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useForkAgent } from "@/lib/hooks/use-fork-agent";
import type { ForkAgentResponse } from "@/lib/marketplace/types";

const NAME_PATTERN = /^[a-z][a-z0-9-]{1,62}$/;

export interface ForkAgentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sourceAgentId: string;
  sourceFqn: string;
  /** Optional list of workspaces the consumer can write to — populates
   *  the workspace-target Select. Pass [] to disable workspace scope. */
  availableWorkspaces?: { id: string; name: string }[];
  onForked?: (response: ForkAgentResponse) => void;
}

export function ForkAgentDialog({
  open,
  onOpenChange,
  sourceAgentId,
  sourceFqn,
  availableWorkspaces = [],
  onForked,
}: ForkAgentDialogProps) {
  const [scope, setScope] = useState<"workspace" | "tenant">("tenant");
  const [workspaceId, setWorkspaceId] = useState<string>("");
  const [newName, setNewName] = useState("");
  const fork = useForkAgent();

  const nameError = newName && !NAME_PATTERN.test(newName)
    ? "Names must start with a letter, contain only lowercase letters, digits, and dashes, and be 2–63 characters."
    : null;

  const canSubmit =
    !!newName &&
    !nameError &&
    (scope === "tenant" || (scope === "workspace" && !!workspaceId)) &&
    !fork.isPending;

  const submit = async () => {
    const body =
      scope === "workspace"
        ? { target_scope: scope as "workspace", target_workspace_id: workspaceId, new_name: newName }
        : { target_scope: scope as "tenant", new_name: newName };
    const response = await fork.mutateAsync({ sourceId: sourceAgentId, body });
    onForked?.(response);
    onOpenChange(false);
    setNewName("");
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Fork {sourceFqn}</DialogTitle>
          <DialogDescription>
            Create an editable copy of this agent in your own tenant or
            workspace. The original is unchanged. Future updates to the
            source will <strong>not</strong> auto-propagate.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="fork-target-scope">Where</Label>
            <Select
              id="fork-target-scope"
              value={scope}
              onChange={(event) => setScope(event.target.value as typeof scope)}
            >
              <option value="tenant">My tenant</option>
              {availableWorkspaces.length > 0 ? (
                <option value="workspace">A specific workspace</option>
              ) : null}
            </Select>
          </div>

          {scope === "workspace" ? (
            <div className="space-y-2">
              <Label htmlFor="fork-target-workspace">Workspace</Label>
              <Select
                id="fork-target-workspace"
                value={workspaceId}
                onChange={(event) => setWorkspaceId(event.target.value)}
              >
                <option value="" disabled>
                  Pick a workspace
                </option>
                {availableWorkspaces.map((ws) => (
                  <option key={ws.id} value={ws.id}>
                    {ws.name}
                  </option>
                ))}
              </Select>
            </div>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="fork-new-name">New name</Label>
            <Input
              id="fork-new-name"
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              placeholder="acme-pdf-extractor"
            />
            {nameError ? (
              <p className="text-sm text-destructive">{nameError}</p>
            ) : null}
          </div>

          {fork.isError ? (
            <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
              Could not create the fork. Try again, or contact support if
              the problem persists.
            </div>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={!canSubmit} onClick={() => void submit()}>
            {fork.isPending ? "Forking…" : "Fork"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
