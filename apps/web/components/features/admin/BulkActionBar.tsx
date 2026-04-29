"use client";

import { ShieldAlert, UserX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AdminWriteButton } from "@/components/features/admin/AdminWriteButton";

interface BulkActionBarProps {
  selectedCount: number;
  onSuspend?: () => void;
  onClear?: () => void;
}

export function BulkActionBar({ selectedCount, onSuspend, onClear }: BulkActionBarProps) {
  if (selectedCount === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border bg-card px-4 py-3">
      <div className="text-sm font-medium">{selectedCount} selected</div>
      <div className="flex flex-wrap items-center gap-2">
        <AdminWriteButton variant="outline" size="sm" onClick={onSuspend}>
          <UserX className="h-4 w-4" />
          Suspend
        </AdminWriteButton>
        <AdminWriteButton variant="outline" size="sm">
          <ShieldAlert className="h-4 w-4" />
          Force MFA
        </AdminWriteButton>
        <Button variant="ghost" size="sm" onClick={onClear}>
          Clear
        </Button>
      </div>
    </div>
  );
}
