"use client";

import { useState } from "react";
import { LifeBuoy, Loader2 } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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

interface Props {
  tenantSlug: string;
  graceEndsAt?: string | null;
  isPending: boolean;
  onConfirm: (vars: { typed_confirmation: string; reason: string }) => void;
  trigger: React.ReactNode;
}

export function TenantRecoveryDialog({
  tenantSlug,
  graceEndsAt,
  isPending,
  onConfirm,
  trigger,
}: Props) {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [reason, setReason] = useState("");
  const matches = typed.trim() === tenantSlug;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <LifeBuoy className="h-5 w-5" />
            Recover tenant
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4 text-sm">
          <Alert>
            <AlertTitle>Recovery window</AlertTitle>
            <AlertDescription>
              Recovery is only possible while the deletion job is in phase 1.
              {graceEndsAt
                ? ` This window ends at ${new Date(graceEndsAt).toLocaleString()}.`
                : ""}
              The cascade workers reverse phase-1 marks and the tenant becomes
              accessible again.
            </AlertDescription>
          </Alert>
          <div className="space-y-2">
            <Label htmlFor="recovery-typed">
              Type tenant slug{" "}
              <span className="font-mono font-semibold">{tenantSlug}</span>
            </Label>
            <Input
              id="recovery-typed"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoComplete="off"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="recovery-reason">Reason (audit logged)</Label>
            <Textarea
              id="recovery-reason"
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
            disabled={!matches || !reason.trim() || isPending}
            onClick={() => {
              onConfirm({
                typed_confirmation: typed.trim(),
                reason: reason.trim(),
              });
              setOpen(false);
            }}
          >
            {isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : null}
            Recover tenant
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
