"use client";

import { useTranslations } from "next-intl";

import { Badge } from "@/components/ui/badge";
import type { UserDsrDetailResponse } from "@/lib/schemas/me";

function formatDate(value: string | null | undefined, emptyLabel: string): string {
  if (!value) {
    return emptyLabel;
  }
  try {
    return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(
      new Date(value),
    );
  } catch {
    return value;
  }
}

function dsrStatusLabel(status: string, labels: Record<string, string>): string {
  return labels[status] ?? status;
}

export function DsrStatusList({ items }: { items: UserDsrDetailResponse[] }) {
  const t = useTranslations("privacy.dsr.status");
  const statusLabels = {
    received: t("states.received"),
    scheduled_with_hold: t("states.scheduled_with_hold"),
    in_progress: t("states.in_progress"),
    completed: t("states.completed"),
    failed: t("states.failed"),
    cancelled: t("states.cancelled"),
  };

  if (items.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card px-4 py-10 text-sm text-muted-foreground">
        {t("empty")}
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      {items.map((item) => (
        <article key={item.id} className="border-b border-border px-4 py-4 last:border-b-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold">{t(`types.${item.request_type}`)}</h2>
            <Badge variant="secondary">{dsrStatusLabel(item.status, statusLabels)}</Badge>
          </div>
          <div className="mt-2 grid gap-1 text-sm text-muted-foreground sm:grid-cols-2">
            <span>{t("filed", { date: formatDate(item.requested_at, t("pending")) })}</span>
            <span>{t("completed", { date: formatDate(item.completed_at, t("pending")) })}</span>
          </div>
        </article>
      ))}
    </div>
  );
}
