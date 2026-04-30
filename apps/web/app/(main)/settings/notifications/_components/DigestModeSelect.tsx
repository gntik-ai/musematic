"use client";

import { useTranslations } from "next-intl";

import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import type { DigestMode, NotificationChannel } from "@/lib/schemas/me";
import { notificationChannels } from "./EventChannelMatrix";

const digestModes: DigestMode[] = ["immediate", "hourly", "daily"];

interface DigestModeSelectProps {
  value: Record<string, DigestMode>;
  onChange: (value: Record<string, DigestMode>) => void;
}

export function DigestModeSelect({ value, onChange }: DigestModeSelectProps) {
  const t = useTranslations("notifications.preferences.digest");

  function update(channel: NotificationChannel, mode: DigestMode) {
    onChange({ ...value, [channel]: mode });
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {notificationChannels.map((channel) => (
        <div key={channel} className="space-y-2">
          <Label htmlFor={`digest-${channel}`}>{t(`channels.${channel}`)}</Label>
          <Select
            id={`digest-${channel}`}
            value={value[channel] ?? "immediate"}
            onChange={(event) => update(channel, event.target.value as DigestMode)}
          >
            {digestModes.map((mode) => (
              <option key={mode} value={mode}>
                {t(`modes.${mode}`)}
              </option>
            ))}
          </Select>
        </div>
      ))}
    </div>
  );
}
