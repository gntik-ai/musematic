"use client";

import { MoreHorizontal } from "lucide-react";
import type { AdminUserRow, UserAction } from "@/lib/types/admin";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const actionLabels: Record<UserAction, string> = {
  approve: "Approve",
  reject: "Reject",
  suspend: "Suspend",
  reactivate: "Reactivate",
};

interface UserActionsMenuProps {
  currentUserId: string | null | undefined;
  onAction: (action: UserAction) => void;
  user: AdminUserRow;
}

export function UserActionsMenu({
  currentUserId,
  onAction,
  user,
}: UserActionsMenuProps) {
  const isSelf = currentUserId === user.id;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          aria-label={`Open actions for ${user.name}`}
          size="icon"
          variant="ghost"
        >
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {user.available_actions.length === 0 ? (
          <DropdownMenuItem disabled>No actions available</DropdownMenuItem>
        ) : null}
        {user.available_actions.map((action) => {
          const disabled = action === "suspend" && isSelf;

          return (
            <DropdownMenuItem
              key={action}
              aria-label={`${actionLabels[action]} ${user.name}`}
              disabled={disabled}
              title={disabled ? "You cannot suspend your own account" : undefined}
              onClick={() => {
                if (!disabled) {
                  onAction(action);
                }
              }}
            >
              {actionLabels[action]}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
