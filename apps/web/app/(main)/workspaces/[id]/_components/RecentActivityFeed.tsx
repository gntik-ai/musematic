"use client";

import { History } from "lucide-react";
import { useTranslations } from "next-intl";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function labelForActivity(item: Record<string, unknown>, fallback: string): string {
  return String(item.event_type ?? item.action ?? item.type ?? fallback);
}

export function RecentActivityFeed({ items }: { items: Record<string, unknown>[] }) {
  const t = useTranslations("workspaces.dashboard");

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <History className="h-4 w-4" />
          {t("cards.recentActivity")}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {items.length ? (
          <ol className="space-y-3">
            {items.slice(0, 10).map((item, index) => (
              <li key={`${labelForActivity(item, t("eventFallback"))}-${index}`} className="rounded-md border p-3">
                <p className="text-sm font-medium">{labelForActivity(item, t("eventFallback"))}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {String(item.created_at ?? item.timestamp ?? t("latestActivity"))}
                </p>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-sm text-muted-foreground">{t("empty")}</p>
        )}
      </CardContent>
    </Card>
  );
}
