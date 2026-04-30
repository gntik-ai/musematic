"use client";

import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Activity } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useUserActivity } from "@/lib/hooks/use-me-activity";
import { ActivityFilters } from "./_components/ActivityFilters";

function toIsoStart(value: string): string | null {
  return value ? new Date(`${value}T00:00:00`).toISOString() : null;
}

function toIsoEnd(value: string): string | null {
  return value ? new Date(`${value}T23:59:59`).toISOString() : null;
}

export default function ActivityPage() {
  const t = useTranslations("security.activity");
  const searchParams = useSearchParams();
  const values = {
    eventType: searchParams.get("eventType") ?? "",
    start: searchParams.get("start") ?? "",
    end: searchParams.get("end") ?? "",
  };
  const activity = useUserActivity({
    event_type: values.eventType || null,
    start_ts: toIsoStart(values.start),
    end_ts: toIsoEnd(values.end),
    limit: 25,
  });
  const entries = activity.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div className="mx-auto w-full max-w-6xl space-y-5">
      <div className="flex items-center gap-3">
        <Activity className="h-6 w-6 text-brand-accent" />
        <div>
          <h1 className="text-2xl font-semibold">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">
            {t("description")}
          </p>
        </div>
      </div>
      <ActivityFilters values={values} />
      <section className="overflow-hidden rounded-lg border border-border bg-card">
        {entries.length === 0 ? (
          <div className="px-4 py-10 text-sm text-muted-foreground">
            {t("empty")}
          </div>
        ) : (
          entries.map((entry) => (
            <article key={entry.id} className="border-b border-border px-4 py-4 last:border-b-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-sm font-semibold">{entry.event_type ?? "audit.event"}</h2>
                <Badge variant="secondary">{entry.severity}</Badge>
                <span className="text-xs text-muted-foreground">{entry.audit_event_source}</span>
              </div>
              <p className="mt-2 text-sm text-muted-foreground">{entry.created_at}</p>
            </article>
          ))
        )}
      </section>
      {activity.hasNextPage ? (
        <Button variant="outline" onClick={() => activity.fetchNextPage()}>
          {t("loadMore")}
        </Button>
      ) : null}
    </div>
  );
}
