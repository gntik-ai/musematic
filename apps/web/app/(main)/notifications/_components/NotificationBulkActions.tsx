"use client";

import { useTranslations } from "next-intl";
import { CheckCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useMarkAllRead } from "@/lib/hooks/use-me-alerts-bulk";

interface NotificationBulkActionsProps {
  allSelected: boolean;
  selectedCount: number;
  totalVisible: number;
  unreadCount: number;
  onToggleSelectAll: (selected: boolean) => void;
}

export function NotificationBulkActions({
  allSelected,
  selectedCount,
  totalVisible,
  unreadCount,
  onToggleSelectAll,
}: NotificationBulkActionsProps) {
  const t = useTranslations("notifications.inbox.bulk");
  const markAllRead = useMarkAllRead();
  const disabled = unreadCount === 0 || markAllRead.isPending;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card px-4 py-3">
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm">
          <input
            checked={allSelected && totalVisible > 0}
            className="h-4 w-4 rounded border border-input accent-[hsl(var(--primary))]"
            disabled={totalVisible === 0}
            type="checkbox"
            onChange={(event) => onToggleSelectAll(event.target.checked)}
          />
          {t("selectPage")}
        </label>
        <p className="text-sm text-muted-foreground">
          {selectedCount > 0
            ? t("selected", { count: selectedCount })
            : t("unread", { count: unreadCount })}
        </p>
      </div>
      <Button
        size="sm"
        variant="outline"
        disabled={disabled}
        onClick={() => markAllRead.mutate(undefined)}
      >
        <CheckCheck className="h-4 w-4" />
        {t("markAllRead")}
      </Button>
    </div>
  );
}
