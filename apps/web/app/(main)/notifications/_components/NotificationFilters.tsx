"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Filter } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";

const readOptions = [
  { value: "all", labelKey: "read.all" },
  { value: "unread", labelKey: "read.unread" },
  { value: "read", labelKey: "read.read" },
] as const;

const severityOptions = ["all", "info", "warning", "critical"] as const;
const channelOptions = ["all", "in_app", "email", "webhook", "slack", "teams", "sms"] as const;

interface NotificationFiltersProps {
  values: {
    read: string;
    severity: string;
    channel: string;
    eventType: string;
    from: string;
    to: string;
  };
}

export function NotificationFilters({ values }: NotificationFiltersProps) {
  const t = useTranslations("notifications.inbox.filters");
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  function updateFilter(key: string, value: string) {
    const next = new URLSearchParams(searchParams.toString());
    if (!value || value === "all") {
      next.delete(key);
    } else {
      next.set(key, value);
    }
    next.delete("cursor");
    router.replace(`${pathname}?${next.toString()}`);
  }

  function resetFilters() {
    router.replace(pathname);
  }

  return (
    <aside className="rounded-lg border border-border bg-card p-4">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-brand-accent" />
          <h2 className="text-sm font-semibold">{t("title")}</h2>
        </div>
        <Button size="sm" variant="ghost" onClick={resetFilters}>
          {t("reset")}
        </Button>
      </div>
      <div className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="notification-read">{t("state")}</Label>
          <Select
            id="notification-read"
            value={values.read}
            onChange={(event) => updateFilter("read", event.target.value)}
          >
            {readOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {t(option.labelKey)}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="notification-severity">{t("severity")}</Label>
          <Select
            id="notification-severity"
            value={values.severity}
            onChange={(event) => updateFilter("severity", event.target.value)}
          >
            {severityOptions.map((option) => (
              <option key={option} value={option}>
                {t(option === "all" ? "options.all" : `severityOptions.${option}`)}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="notification-channel">{t("channel")}</Label>
          <Select
            id="notification-channel"
            value={values.channel}
            onChange={(event) => updateFilter("channel", event.target.value)}
          >
            {channelOptions.map((option) => (
              <option key={option} value={option}>
                {t(option === "all" ? "options.all" : `channels.${option}`)}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="notification-event-type">{t("eventType")}</Label>
          <Input
            id="notification-event-type"
            placeholder="workspace.updated"
            value={values.eventType}
            onChange={(event) => updateFilter("eventType", event.target.value)}
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-2">
            <Label htmlFor="notification-from">{t("from")}</Label>
            <Input
              id="notification-from"
              type="date"
              value={values.from}
              onChange={(event) => updateFilter("from", event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="notification-to">{t("to")}</Label>
            <Input
              id="notification-to"
              type="date"
              value={values.to}
              onChange={(event) => updateFilter("to", event.target.value)}
            />
          </div>
        </div>
      </div>
    </aside>
  );
}
