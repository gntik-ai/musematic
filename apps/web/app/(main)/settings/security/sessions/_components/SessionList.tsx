"use client";

import { useTranslations } from "next-intl";
import { Laptop, Smartphone, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useRevokeSession } from "@/lib/hooks/use-me-sessions";
import type { UserSessionDetail } from "@/lib/schemas/me";

function deviceIcon(deviceInfo: string | null | undefined) {
  const normalized = (deviceInfo ?? "").toLowerCase();
  return normalized.includes("mobile") || normalized.includes("phone") ? (
    <Smartphone className="h-4 w-4 text-brand-accent" />
  ) : (
    <Laptop className="h-4 w-4 text-brand-accent" />
  );
}

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

export function SessionList({ sessions }: { sessions: UserSessionDetail[] }) {
  const t = useTranslations("security.sessions.list");
  const revoke = useRevokeSession();

  if (sessions.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card px-4 py-10 text-center text-sm text-muted-foreground">
        {t("empty")}
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      {sessions.map((session) => (
        <article
          key={session.session_id}
          className="grid gap-3 border-b border-border px-4 py-4 last:border-b-0 sm:grid-cols-[1fr_auto]"
        >
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              {deviceIcon(session.device_info)}
              <h2 className="truncate text-sm font-semibold">
                {session.device_info ?? t("unknownDevice")}
              </h2>
              {session.is_current ? <Badge variant="outline">{t("current")}</Badge> : null}
            </div>
            <div className="mt-2 grid gap-1 text-sm text-muted-foreground sm:grid-cols-2">
              <span>{session.location ?? session.ip_address ?? t("unknownLocation")}</span>
              <span>
                {t("lastActive", { date: formatDate(session.last_activity, t("unknown")) })}
              </span>
              <span>{t("created", { date: formatDate(session.created_at, t("unknown")) })}</span>
              <span className="font-mono text-xs">{session.session_id}</span>
            </div>
          </div>
          <Button
            aria-label={t("revokeAria", { sessionId: session.session_id })}
            disabled={session.is_current || revoke.isPending}
            size="sm"
            variant="outline"
            onClick={() => revoke.mutate(session.session_id)}
          >
            <Trash2 className="h-4 w-4" />
            {t("revoke")}
          </Button>
        </article>
      ))}
    </div>
  );
}
