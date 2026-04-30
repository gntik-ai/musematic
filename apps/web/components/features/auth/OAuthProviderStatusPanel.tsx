"use client";

import { Activity, Link2, TimerReset } from "lucide-react";
import { useTranslations } from "next-intl";
import { useAdminOAuthProviderStatus } from "@/lib/hooks/use-oauth";
import type { OAuthProviderAdminResponse } from "@/lib/types/oauth";

function formatTimestamp(value: string | null, fallback: string): string {
  if (!value) {
    return fallback;
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function OAuthProviderStatusPanel({
  provider,
}: {
  provider: OAuthProviderAdminResponse;
}) {
  const t = useTranslations("admin.oauth");
  const query = useAdminOAuthProviderStatus(provider.provider_type);
  const status = query.data;
  const items = [
    {
      label: t("status.lastAuth"),
      value: formatTimestamp(
        status?.last_successful_auth_at ?? provider.last_successful_auth_at,
        t("status.never"),
      ),
      icon: TimerReset,
    },
    {
      label: t("status.auth24h"),
      value: String(status?.auth_count_24h ?? 0),
      icon: Activity,
    },
    {
      label: t("status.auth7d"),
      value: String(status?.auth_count_7d ?? 0),
      icon: Activity,
    },
    {
      label: t("status.auth30d"),
      value: String(status?.auth_count_30d ?? 0),
      icon: Activity,
    },
    {
      label: t("status.linkedUsers"),
      value: String(status?.active_linked_users ?? 0),
      icon: Link2,
    },
  ];

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <div
            className="min-h-24 rounded-md border border-border bg-background p-4"
            key={item.label}
          >
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Icon className="h-4 w-4" />
              <span>{item.label}</span>
            </div>
            <p className="mt-3 break-words text-lg font-semibold">{item.value}</p>
          </div>
        );
      })}
      {query.isError ? (
        <p className="md:col-span-2 xl:col-span-4 text-sm text-destructive">
          {t("status.loadFailed")}
        </p>
      ) : null}
    </div>
  );
}
