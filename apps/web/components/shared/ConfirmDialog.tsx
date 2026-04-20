"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "default" | "destructive";
  isLoading?: boolean;
  requireTypedConfirmation?: string;
  onConfirm: () => void;
  onOpenChange: (open: boolean) => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  variant = "default",
  isLoading = false,
  requireTypedConfirmation,
  onConfirm,
  onOpenChange,
}: ConfirmDialogProps) {
  const [typedValue, setTypedValue] = useState("");

  useEffect(() => {
    if (!open) {
      setTypedValue("");
    }
  }, [open]);

  const typedConfirmationMatches =
    !requireTypedConfirmation || typedValue === requireTypedConfirmation;

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        {requireTypedConfirmation ? (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              Type <span className="font-mono font-medium text-foreground">{requireTypedConfirmation}</span> to confirm.
            </p>
            <Input
              value={typedValue}
              onChange={(event) => setTypedValue(event.target.value)}
              placeholder={requireTypedConfirmation}
            />
          </div>
        ) : null}
        <AlertDialogFooter>
          <AlertDialogCancel className="rounded-md border border-border px-4 py-2 text-sm" disabled={isLoading}>
            {cancelLabel}
          </AlertDialogCancel>
          <Button
            disabled={isLoading || !typedConfirmationMatches}
            variant={variant === "destructive" ? "destructive" : "default"}
            onClick={onConfirm}
          >
            {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {confirmLabel}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
