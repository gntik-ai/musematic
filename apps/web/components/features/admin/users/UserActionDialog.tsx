"use client";

import { Loader2 } from "lucide-react";
import type { AdminUserRow, UserAction } from "@/lib/types/admin";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";

const dialogCopy: Record<
  UserAction,
  { title: string; description: string; confirmLabel: string }
> = {
  approve: {
    title: "Grant platform access",
    description:
      "Approve this account and allow the user to access the platform immediately.",
    confirmLabel: "Approve user",
  },
  reject: {
    title: "Block account and send rejection email",
    description:
      "Reject this account request. The user will remain blocked until an administrator changes the decision.",
    confirmLabel: "Reject user",
  },
  suspend: {
    title: "Invalidate active sessions",
    description:
      "Suspend the account and invalidate any currently active sessions.",
    confirmLabel: "Suspend user",
  },
  reactivate: {
    title: "Restore platform access",
    description:
      "Reactivate this account and restore the user's ability to sign in.",
    confirmLabel: "Reactivate user",
  },
};

interface UserActionDialogProps {
  action: UserAction | null;
  isPending: boolean;
  onConfirm: () => void;
  onOpenChange: (open: boolean) => void;
  open: boolean;
  user: AdminUserRow | null;
}

export function UserActionDialog({
  action,
  isPending,
  onConfirm,
  onOpenChange,
  open,
  user,
}: UserActionDialogProps) {
  if (!action || !user) {
    return null;
  }

  const copy = dialogCopy[action];

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{copy.title}</AlertDialogTitle>
          <AlertDialogDescription>
            {user.name} ({user.email})
          </AlertDialogDescription>
          <AlertDialogDescription>{copy.description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <Button
            disabled={isPending}
            variant="ghost"
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button
            disabled={isPending}
            variant={action === "reject" || action === "suspend" ? "destructive" : "default"}
            onClick={onConfirm}
          >
            {isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Processing…
              </>
            ) : (
              copy.confirmLabel
            )}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
