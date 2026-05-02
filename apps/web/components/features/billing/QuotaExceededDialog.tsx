"use client";

import Link from "next/link";
import { AlertTriangle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import type { QuotaError } from "@/lib/api";

interface QuotaExceededDialogProps {
  error: QuotaError | null;
  workspaceId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function value(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "0";
  }
  return String(value);
}

function resetText(value?: string | null): string {
  if (!value) {
    return "Current billing period";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function QuotaExceededDialog({
  error,
  workspaceId,
  open,
  onOpenChange,
}: QuotaExceededDialogProps) {
  const details = error?.quota ?? {};
  const upgradeUrl = details.upgrade_url ?? `/workspaces/${workspaceId}/billing/upgrade`;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-destructive" />
            Quota exceeded
          </DialogTitle>
          <DialogDescription>
            {error?.message ?? "This workspace has reached a billing quota."}
          </DialogDescription>
        </DialogHeader>
        <dl className="grid gap-3 rounded-md border p-4 text-sm">
          <div className="flex items-center justify-between gap-4">
            <dt className="text-muted-foreground">Quota</dt>
            <dd className="font-medium">{details.quota_name ?? "Workspace quota"}</dd>
          </div>
          <div className="flex items-center justify-between gap-4">
            <dt className="text-muted-foreground">Usage</dt>
            <dd className="font-medium">
              {value(details.current)} / {value(details.limit)}
            </dd>
          </div>
          <div className="flex items-center justify-between gap-4">
            <dt className="text-muted-foreground">Resets</dt>
            <dd className="text-right font-medium">{resetText(details.reset_at)}</dd>
          </div>
          <div className="flex items-center justify-between gap-4">
            <dt className="text-muted-foreground">Plan</dt>
            <dd className="font-medium">{details.plan_slug ?? "Current plan"}</dd>
          </div>
        </dl>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Dismiss
          </Button>
          <Button asChild>
            <Link href={upgradeUrl}>Upgrade to Pro</Link>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
