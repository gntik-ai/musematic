"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Bell } from "lucide-react";

import { fetchUserAlerts, meQueryKeys } from "@/lib/api/me";
import { useAppQuery } from "@/lib/hooks/use-api";
import type { UserAlertItem } from "@/lib/schemas/me";
import { NotificationBulkActions } from "./_components/NotificationBulkActions";
import { NotificationFilters } from "./_components/NotificationFilters";
import { NotificationListItem } from "./_components/NotificationListItem";

type AlertReadFilter = "all" | "read" | "unread";

function readParam(value: string | null): AlertReadFilter {
  return value === "read" || value === "unread" ? value : "all";
}

function sourceChannel(alert: UserAlertItem): string | null {
  const channel = alert.source_reference?.channel;
  return typeof channel === "string" ? channel : null;
}

function isWithinDateRange(alert: UserAlertItem, from: string, to: string): boolean {
  const created = new Date(alert.created_at).getTime();
  if (Number.isNaN(created)) {
    return true;
  }
  if (from && created < new Date(`${from}T00:00:00`).getTime()) {
    return false;
  }
  if (to && created > new Date(`${to}T23:59:59`).getTime()) {
    return false;
  }
  return true;
}

function filterAlerts(
  items: UserAlertItem[],
  values: {
    severity: string;
    channel: string;
    eventType: string;
    from: string;
    to: string;
  },
) {
  return items.filter((alert) => {
    if (values.severity !== "all" && alert.urgency !== values.severity) {
      return false;
    }
    if (values.channel !== "all" && sourceChannel(alert) !== values.channel) {
      return false;
    }
    if (values.eventType && !alert.alert_type.includes(values.eventType)) {
      return false;
    }
    return isWithinDateRange(alert, values.from, values.to);
  });
}

export default function NotificationsPage() {
  const t = useTranslations("notifications.inbox");
  const searchParams = useSearchParams();
  const filters = {
    read: readParam(searchParams.get("read")),
    severity: searchParams.get("severity") ?? "all",
    channel: searchParams.get("channel") ?? "all",
    eventType: searchParams.get("eventType") ?? "",
    from: searchParams.get("from") ?? "",
    to: searchParams.get("to") ?? "",
  };
  const cursor = searchParams.get("cursor");
  const alertFilters = { read: filters.read, limit: 50, cursor };
  const alertsQuery = useAppQuery(
    meQueryKeys.alerts(alertFilters),
    () => fetchUserAlerts(alertFilters),
  );
  const alerts = alertsQuery.data?.items ?? [];
  const visibleAlerts = useMemo(() => filterAlerts(alerts, filters), [alerts, filters]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const unreadCount = alertsQuery.data?.total_unread ?? 0;
  const allVisibleSelected =
    visibleAlerts.length > 0 && visibleAlerts.every((alert) => selectedIds.has(alert.id));

  useEffect(() => {
    setSelectedIds((current) => {
      const visibleIds = new Set(visibleAlerts.map((alert) => alert.id));
      const next = new Set([...current].filter((id) => visibleIds.has(id)));
      return next.size === current.size ? current : next;
    });
  }, [visibleAlerts]);

  function toggleSelection(alertId: string, selected: boolean) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (selected) {
        next.add(alertId);
      } else {
        next.delete(alertId);
      }
      return next;
    });
  }

  function toggleSelectAll(selected: boolean) {
    setSelectedIds(selected ? new Set(visibleAlerts.map((alert) => alert.id)) : new Set());
  }

  return (
    <div className="mx-auto w-full max-w-7xl space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <Bell className="h-6 w-6 text-brand-accent" />
          <div>
            <h1 className="text-2xl font-semibold">{t("title")}</h1>
            <p className="text-sm text-muted-foreground">
              {t("description")}
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-[280px_1fr]">
        <NotificationFilters values={filters} />
        <main className="space-y-4">
          <NotificationBulkActions
            allSelected={allVisibleSelected}
            selectedCount={selectedIds.size}
            totalVisible={visibleAlerts.length}
            unreadCount={unreadCount}
            onToggleSelectAll={toggleSelectAll}
          />
          <section className="overflow-hidden rounded-lg border border-border bg-card">
            {alertsQuery.isLoading ? (
              <div className="px-4 py-10 text-sm text-muted-foreground">
                {t("loading")}
              </div>
            ) : visibleAlerts.length === 0 ? (
              <div className="px-4 py-10 text-sm text-muted-foreground">
                {t("empty")}
              </div>
            ) : (
              visibleAlerts.map((alert) => (
                <NotificationListItem
                  key={alert.id}
                  alert={alert}
                  selected={selectedIds.has(alert.id)}
                  onSelectedChange={(selected) => toggleSelection(alert.id, selected)}
                />
              ))
            )}
          </section>
        </main>
      </div>
    </div>
  );
}
