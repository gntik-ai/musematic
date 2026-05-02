"use client";

import { useEffect, useMemo } from "react";
import { Bell, BellOff } from "lucide-react";
import { useTranslations } from "next-intl";
import {
  extractAlertInteractionId,
  isInteractionAlertMuted,
} from "@/lib/alerts/interaction-mutes";
import { createApiClient } from "@/lib/api";
import { useAlertFeed } from "@/lib/hooks/use-alert-feed";
import { useAppQuery } from "@/lib/hooks/use-api";
import { useAlertStore } from "@/store/alert-store";
import { useAuthStore } from "@/store/auth-store";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const api = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

interface AlertListItem {
  id: string;
  alert_type: string;
  title: string;
  body: string | null;
  read: boolean;
  interaction_id?: string | null;
  source_reference: { id?: string; kind?: string; url?: string; deep_link?: string } | null;
  created_at: string;
}

interface AlertListResponse {
  items: AlertListItem[];
  total_unread: number;
}

interface UnreadCountResponse {
  count: number;
}

const CONTRACT_TEMPLATE_UPSTREAM_UPDATED = "creator.contract_template.upstream_updated";

function formatTimestamp(value: string): string {
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

export function NotificationBell() {
  const templateT = useTranslations("creator.template");
  const { isConnected } = useAlertFeed();
  const userId = useAuthStore((state) => state.user?.id ?? null);
  const unreadCount = useAlertStore((state) => state.unreadCount);
  const setUnreadCount = useAlertStore((state) => state.setUnreadCount);
  const isDropdownOpen = useAlertStore((state) => state.isDropdownOpen);
  const setDropdownOpen = useAlertStore((state) => state.setDropdownOpen);

  const alertsQuery = useAppQuery<AlertListResponse>(
    ["alert-feed", userId ?? "none"],
    () => api.get<AlertListResponse>("/me/alerts?limit=5"),
    { enabled: Boolean(userId), staleTime: 15_000 },
  );
  const unreadQuery = useAppQuery<UnreadCountResponse>(
    ["alert-unread", userId ?? "none"],
    () => api.get<UnreadCountResponse>("/me/alerts/unread-count"),
    { enabled: Boolean(userId), staleTime: 15_000 },
  );

  useEffect(() => {
    if (typeof unreadQuery.data?.count === "number") {
      setUnreadCount(unreadQuery.data.count);
    }
  }, [setUnreadCount, unreadQuery.data?.count]);

  const items = alertsQuery.data?.items ?? [];
  const visibleItems = useMemo(
    () =>
      userId
        ? items.filter(
            (alert) =>
              !isInteractionAlertMuted(
                userId,
                extractAlertInteractionId(alert),
              ),
          )
        : items,
    [items, userId],
  );

  return (
    <DropdownMenu open={isDropdownOpen} onOpenChange={setDropdownOpen}>
      <DropdownMenuTrigger asChild>
        <Button aria-label="Notifications" className="relative" size="icon" variant="ghost">
          {isConnected ? <Bell className="h-4 w-4" /> : <BellOff className="h-4 w-4" />}
          {unreadCount > 0 ? (
            <Badge className="absolute -right-1 -top-1 h-5 min-w-5 justify-center rounded-full px-1 text-[10px]" variant="destructive">
              {unreadCount > 99 ? "99+" : unreadCount}
            </Badge>
          ) : null}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[360px] max-w-[calc(100vw-2rem)]">
        <DropdownMenuLabel className="flex items-center justify-between gap-3">
          <span>Notifications</span>
          <span aria-live="polite" className="text-xs font-normal text-muted-foreground">
            {isConnected ? `${unreadCount} unread` : "Realtime disconnected"}
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {visibleItems.length === 0 ? (
          <div className="px-2 py-6 text-sm text-muted-foreground">
            No alerts yet.
          </div>
        ) : (
          visibleItems.map((alert) => {
            const href = alert.source_reference?.url;
            const deepLink = href ?? alert.source_reference?.deep_link;
            const isTemplateUpdate = alert.alert_type === CONTRACT_TEMPLATE_UPSTREAM_UPDATED;
            const isBillingOverage = alert.alert_type === "billing.overage.required";
            return (
              <DropdownMenuItem
                className="block text-left"
                key={alert.id}
                onClick={() => {
                  if (deepLink) {
                    window.location.assign(deepLink);
                  }
                }}
              >
                <div className="space-y-1">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium">{alert.title}</span>
                    {isBillingOverage ? <Badge variant="destructive">Overage</Badge> : null}
                    {!alert.read ? <Badge variant="outline">New</Badge> : null}
                  </div>
                  {alert.body ? (
                    <p className="line-clamp-2 text-xs text-muted-foreground">{alert.body}</p>
                  ) : null}
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-[11px] text-muted-foreground">{formatTimestamp(alert.created_at)}</p>
                    {deepLink && isBillingOverage ? (
                      <span className="text-[11px] font-medium text-destructive">
                        Authorise now
                      </span>
                    ) : null}
                    {deepLink && isTemplateUpdate ? (
                      <span className="text-[11px] font-medium text-brand-accent">
                        {templateT("viewDiff")}
                      </span>
                    ) : null}
                  </div>
                </div>
              </DropdownMenuItem>
            );
          })
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          className="justify-center font-medium"
          onClick={() => window.location.assign("/notifications")}
        >
          See all
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
