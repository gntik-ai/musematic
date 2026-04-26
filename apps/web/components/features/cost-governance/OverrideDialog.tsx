"use client";

import { useMemo, useState } from "react";
import { KeyRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

interface OverrideDialogProps {
  isSubmitting?: boolean;
  override?: { token: string; expires_at: string } | null;
  onIssue: (reason: string) => void;
}

export function OverrideDialog({
  isSubmitting = false,
  onIssue,
  override,
}: OverrideDialogProps) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const expiryLabel = useMemo(() => {
    if (!override) {
      return null;
    }
    return new Date(override.expires_at).toLocaleTimeString();
  }, [override]);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline">
          <KeyRound className="mr-2 h-4 w-4" />
          Request override
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Budget override</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Label htmlFor="override-reason">Reason</Label>
          <Textarea
            id="override-reason"
            minLength={1}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
          {override ? (
            <div className="rounded-lg border bg-muted p-3 text-sm">
              <p className="font-mono text-xs break-all">{override.token}</p>
              <p className="mt-2 text-muted-foreground">Expires at {expiryLabel}</p>
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button disabled={isSubmitting || reason.trim().length === 0} onClick={() => onIssue(reason)}>
            Issue token
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
