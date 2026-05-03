"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

interface ConfirmDeleteDialogProps {
  workspaceName: string;
  onConfirm: (vars: { typed_confirmation: string; reason?: string }) => void;
  isPending: boolean;
  trigger: React.ReactNode;
}

export function ConfirmDeleteDialog({
  workspaceName,
  onConfirm,
  isPending,
  trigger,
}: ConfirmDeleteDialogProps) {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [reason, setReason] = useState("");
  const matches = typed.trim() === workspaceName;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete workspace</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 text-sm">
          <p>
            This will start a 7-day grace period. After that, all agents,
            executions, audit history, costs, and members are permanently
            deleted. You will receive a cancel link by email valid for 7 days.
          </p>
          <div className="space-y-2">
            <Label htmlFor="typed-confirmation">
              Type <span className="font-mono font-semibold">{workspaceName}</span> to confirm
            </Label>
            <Input
              id="typed-confirmation"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoComplete="off"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="deletion-reason">Reason (optional)</Label>
            <Textarea
              id="deletion-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={!matches || isPending}
            onClick={() => {
              const payload: { typed_confirmation: string; reason?: string } = {
                typed_confirmation: typed.trim(),
              };
              const trimmedReason = reason.trim();
              if (trimmedReason) payload.reason = trimmedReason;
              onConfirm(payload);
              setOpen(false);
            }}
          >
            {isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Schedule deletion
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
