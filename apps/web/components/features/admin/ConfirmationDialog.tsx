"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { AdminWriteButton } from "@/components/features/admin/AdminWriteButton";
import { TwoPersonAuthDialog } from "@/components/features/admin/TwoPersonAuthDialog";

interface ConfirmationDialogProps {
  open: boolean;
  variant: "simple" | "typed" | "2pa";
  title: string;
  phrase?: string;
  action?: string;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}

export function ConfirmationDialog({
  open,
  variant,
  title,
  phrase = "CONFIRM",
  action = "admin.action",
  onOpenChange,
  onConfirm,
}: ConfirmationDialogProps) {
  const [typed, setTyped] = useState("");
  if (variant === "2pa") {
    return (
      <TwoPersonAuthDialog
        open={open}
        mode="initiate"
        action={action}
        onOpenChange={onOpenChange}
        onConfirm={onConfirm}
      />
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        {variant === "typed" ? (
          <Input value={typed} onChange={(event) => setTyped(event.target.value)} placeholder={phrase} />
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <AdminWriteButton
            variant="destructive"
            disabled={variant === "typed" && typed !== phrase}
            onClick={onConfirm}
          >
            Confirm
          </AdminWriteButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
