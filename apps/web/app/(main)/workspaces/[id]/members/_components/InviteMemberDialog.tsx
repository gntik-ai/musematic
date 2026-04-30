"use client";

import { useState } from "react";
import { UserPlus2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useInviteWorkspaceMember } from "@/lib/hooks/use-workspace-members";
import type { WorkspaceMember } from "@/lib/schemas/workspace-owner";

const roles: WorkspaceMember["role"][] = ["admin", "member", "viewer"];

export function InviteMemberDialog({ workspaceId }: { workspaceId: string }) {
  const [open, setOpen] = useState(false);
  const [userId, setUserId] = useState("");
  const [role, setRole] = useState<WorkspaceMember["role"]>("member");
  const invite = useInviteWorkspaceMember(workspaceId);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <UserPlus2 className="h-4 w-4" />
          Invite
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite workspace member</DialogTitle>
          <DialogDescription>
            Add an existing platform user to this workspace with the selected role.
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            invite.mutate(
              { user_id: userId, role },
              {
                onSuccess: () => {
                  setUserId("");
                  setRole("member");
                  setOpen(false);
                },
              },
            );
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="member-user-id">User ID</Label>
            <Input
              id="member-user-id"
              onChange={(event) => setUserId(event.target.value)}
              placeholder="00000000-0000-0000-0000-000000000000"
              value={userId}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="member-role">Role</Label>
            <Select
              id="member-role"
              value={role}
              onChange={(event) => setRole(event.target.value as WorkspaceMember["role"])}
            >
              {roles.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </Select>
          </div>
          <Button disabled={!userId || invite.isPending} type="submit">
            Add member
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
