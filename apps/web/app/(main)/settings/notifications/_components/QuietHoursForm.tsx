"use client";

import { useTranslations } from "next-intl";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { QuietHours } from "@/lib/schemas/me";

interface QuietHoursFormProps {
  value: QuietHours | null | undefined;
  onChange: (value: QuietHours | null) => void;
}

export function QuietHoursForm({ value, onChange }: QuietHoursFormProps) {
  const t = useTranslations("notifications.preferences.quietHours");
  const current = value ?? { start_time: "", end_time: "", timezone: Intl.DateTimeFormat().resolvedOptions().timeZone };

  function update(partial: Partial<QuietHours>) {
    const next = { ...current, ...partial };
    if (!next.start_time && !next.end_time) {
      onChange(null);
      return;
    }
    onChange(next);
  }

  return (
    <div className="grid gap-3 sm:grid-cols-3">
      <div className="space-y-2">
        <Label htmlFor="quiet-start">{t("start")}</Label>
        <Input
          id="quiet-start"
          type="time"
          value={current.start_time}
          onChange={(event) => update({ start_time: event.target.value })}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="quiet-end">{t("end")}</Label>
        <Input
          id="quiet-end"
          type="time"
          value={current.end_time}
          onChange={(event) => update({ end_time: event.target.value })}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="quiet-timezone">{t("timezone")}</Label>
        <Input
          id="quiet-timezone"
          value={current.timezone}
          onChange={(event) => update({ timezone: event.target.value })}
        />
      </div>
    </div>
  );
}
