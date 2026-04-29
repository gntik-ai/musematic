"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { PreferencesFormValues } from "@/components/features/preferences/preferences-schema";

type NotificationPreferences = PreferencesFormValues["notification_preferences"];

interface NotificationPreferencesSectionProps {
  value: NotificationPreferences;
  onChange: (value: NotificationPreferences) => void;
}

export function NotificationPreferencesSection({
  value,
  onChange,
}: NotificationPreferencesSectionProps) {
  function update<K extends keyof NotificationPreferences>(
    key: K,
    nextValue: NotificationPreferences[K],
  ) {
    onChange({ ...value, [key]: nextValue });
  }

  return (
    <fieldset className="space-y-4">
      <legend className="text-sm font-semibold">Notification preferences</legend>
      <div className="grid gap-3 sm:grid-cols-3">
        {[
          ["email", "Email"],
          ["in_app", "In-app"],
          ["mobile_push", "Mobile push"],
        ].map(([key, label]) => (
          <Label key={key} className="flex items-center gap-2 rounded-lg border border-border p-3">
            <input
              checked={Boolean(value[key as keyof NotificationPreferences])}
              className="h-4 w-4 accent-primary"
              type="checkbox"
              onChange={(event) =>
                update(key as keyof NotificationPreferences, event.target.checked as never)
              }
            />
            {label}
          </Label>
        ))}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="quiet-hours-start">Quiet hours start</Label>
          <Input
            id="quiet-hours-start"
            type="time"
            value={value.quiet_hours_start}
            onChange={(event) => update("quiet_hours_start", event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="quiet-hours-end">Quiet hours end</Label>
          <Input
            id="quiet-hours-end"
            type="time"
            value={value.quiet_hours_end}
            onChange={(event) => update("quiet_hours_end", event.target.value)}
          />
        </div>
      </div>
    </fieldset>
  );
}
