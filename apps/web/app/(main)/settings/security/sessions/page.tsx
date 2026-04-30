"use client";

import { MonitorX } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { useRevokeOtherSessions, useUserSessions } from "@/lib/hooks/use-me-sessions";
import { SessionList } from "./_components/SessionList";

export default function SessionsPage() {
  const t = useTranslations("security.sessions");
  const sessions = useUserSessions();
  const revokeOthers = useRevokeOtherSessions();
  const items = sessions.data?.items ?? [];
  const otherCount = items.filter((item) => !item.is_current).length;

  return (
    <div className="mx-auto w-full max-w-6xl space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <MonitorX className="h-6 w-6 text-brand-accent" />
          <div>
            <h1 className="text-2xl font-semibold">{t("title")}</h1>
            <p className="text-sm text-muted-foreground">
              {t("description")}
            </p>
          </div>
        </div>
        <Button
          disabled={otherCount === 0 || revokeOthers.isPending}
          variant="outline"
          onClick={() => revokeOthers.mutate(undefined)}
        >
          {t("revokeOthers")}
        </Button>
      </div>
      <SessionList sessions={items} />
    </div>
  );
}
