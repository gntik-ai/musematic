"use client";

import { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
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
import { useChallenge, useConsumeChallenge } from "@/lib/hooks/use-2pa-challenge";
import { useTransferWorkspaceOwnership } from "@/lib/hooks/use-workspace-members";

export function TransferOwnershipDialog({ workspaceId }: { workspaceId: string }) {
  const [open, setOpen] = useState(false);
  const [newOwnerId, setNewOwnerId] = useState("");
  const [challengeId, setChallengeId] = useState<string | null>(null);
  const transfer = useTransferWorkspaceOwnership(workspaceId);
  const challenge = useChallenge(challengeId, { poll: Boolean(challengeId) });
  const consume = useConsumeChallenge();
  const approved = challenge.data?.status === "approved";

  useEffect(() => {
    if (!open) {
      setChallengeId(null);
      setNewOwnerId("");
    }
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          <ShieldCheck className="h-4 w-4" />
          Transfer ownership
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Transfer workspace ownership</DialogTitle>
          <DialogDescription>
            Ownership transfer creates a server-side 2PA challenge that a platform admin must approve.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="new-owner-id">New owner ID</Label>
            <Input
              id="new-owner-id"
              onChange={(event) => setNewOwnerId(event.target.value)}
              placeholder="00000000-0000-0000-0000-000000000000"
              value={newOwnerId}
            />
          </div>

          <Button
            disabled={!newOwnerId || transfer.isPending || Boolean(challengeId)}
            onClick={() => {
              transfer.mutate(newOwnerId, {
                onSuccess: (result) => setChallengeId(result.challenge_id),
              });
            }}
          >
            Initiate 2PA challenge
          </Button>

          {challengeId ? (
            <div className="rounded-md border p-3 text-sm">
              <p className="font-medium">Challenge {challenge.data?.status ?? "pending"}</p>
              <p className="mt-1 text-xs text-muted-foreground">{challengeId}</p>
              <p className="mt-2 text-xs text-muted-foreground">
                Expires {challenge.data?.expires_at ?? transfer.data?.expires_at}
              </p>
            </div>
          ) : null}

          <Button
            disabled={!approved || consume.isPending || !challengeId}
            onClick={() => {
              if (!challengeId) {
                return;
              }
              consume.mutate(challengeId, {
                onSuccess: () => setOpen(false),
              });
            }}
          >
            Consume approved challenge
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
