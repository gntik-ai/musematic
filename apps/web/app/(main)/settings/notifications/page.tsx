"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { BellRing, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  useNotificationPreferences,
  useUpdateNotificationPreferences,
} from "@/lib/hooks/use-me-notification-preferences";
import type {
  DigestMode,
  NotificationChannel,
  QuietHours,
} from "@/lib/schemas/me";
import { DigestModeSelect } from "./_components/DigestModeSelect";
import {
  EventChannelMatrix,
  notificationEvents,
} from "./_components/EventChannelMatrix";
import { QuietHoursForm } from "./_components/QuietHoursForm";
import { TestNotificationButton } from "./_components/TestNotificationButton";

export default function NotificationPreferencesPage() {
  const t = useTranslations("notifications.preferences");
  const preferences = useNotificationPreferences();
  const updatePreferences = useUpdateNotificationPreferences();
  const [perChannel, setPerChannel] = useState<Record<string, NotificationChannel[]>>({});
  const [digestMode, setDigestMode] = useState<Record<string, DigestMode>>({});
  const [quietHours, setQuietHours] = useState<QuietHours | null>(null);

  useEffect(() => {
    if (preferences.data) {
      setPerChannel(preferences.data.per_channel_preferences);
      setDigestMode(preferences.data.digest_mode);
      setQuietHours(preferences.data.quiet_hours ?? null);
    }
  }, [preferences.data]);

  function save() {
    updatePreferences.mutate({
      per_channel_preferences: perChannel,
      digest_mode: digestMode,
      quiet_hours: quietHours,
    });
  }

  return (
    <div className="mx-auto w-full max-w-7xl space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <BellRing className="h-6 w-6 text-brand-accent" />
          <div>
            <h1 className="text-2xl font-semibold">{t("title")}</h1>
            <p className="text-sm text-muted-foreground">
              {t("description")}
            </p>
          </div>
        </div>
        <Button disabled={updatePreferences.isPending || preferences.isLoading} onClick={save}>
          <Save className="h-4 w-4" />
          {t("save")}
        </Button>
      </div>

      <section className="space-y-4 rounded-lg border border-border bg-card p-4">
        <div>
          <h2 className="text-sm font-semibold">{t("eventChannels.title")}</h2>
          <p className="text-sm text-muted-foreground">
            {t("eventChannels.description")}
          </p>
        </div>
        <EventChannelMatrix value={perChannel} onChange={setPerChannel} />
      </section>

      <section className="space-y-4 rounded-lg border border-border bg-card p-4">
        <div>
          <h2 className="text-sm font-semibold">{t("digest.title")}</h2>
          <p className="text-sm text-muted-foreground">{t("digest.description")}</p>
        </div>
        <DigestModeSelect value={digestMode} onChange={setDigestMode} />
      </section>

      <section className="space-y-4 rounded-lg border border-border bg-card p-4">
        <div>
          <h2 className="text-sm font-semibold">{t("quietHours.title")}</h2>
          <p className="text-sm text-muted-foreground">
            {t("quietHours.description")}
          </p>
        </div>
        <QuietHoursForm value={quietHours} onChange={setQuietHours} />
      </section>

      <section className="space-y-4 rounded-lg border border-border bg-card p-4">
        <div>
          <h2 className="text-sm font-semibold">{t("testEvents.title")}</h2>
          <p className="text-sm text-muted-foreground">{t("testEvents.description")}</p>
        </div>
        <Separator />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {notificationEvents.map((eventType) => (
            <div
              key={eventType}
              className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2"
            >
              <span className="min-w-0 truncate text-sm">{eventType}</span>
              <TestNotificationButton eventType={eventType} />
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
