"use client";

import { ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";

interface TwoPersonAuthDialogProps {
  open: boolean;
  mode: "initiate" | "approve";
  action: string;
  payload?: Record<string, unknown>;
  onOpenChange: (open: boolean) => void;
  onConfirm?: () => void;
}

export function TwoPersonAuthDialog({
  open,
  mode,
  action,
  payload,
  onOpenChange,
  onConfirm,
}: TwoPersonAuthDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5" />
            {mode === "initiate" ? "Request approval" : "Approve request"}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="rounded-md border bg-muted/40 p-3 font-mono text-xs">{action}</div>
          {payload ? (
            <pre className="max-h-48 overflow-auto rounded-md border bg-muted/40 p-3 text-xs">
              {JSON.stringify(payload, null, 2)}
            </pre>
          ) : null}
          <Textarea placeholder="Re-authentication or approval note" />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={onConfirm}>{mode === "initiate" ? "Request" : "Approve"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
