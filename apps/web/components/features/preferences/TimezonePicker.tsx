"use client";

import { useMemo } from "react";
import { Input } from "@/components/ui/input";

const fallbackTimezones = ["UTC", "Europe/Madrid", "Europe/Berlin", "America/New_York", "America/Los_Angeles", "Asia/Tokyo", "Asia/Shanghai"];

function getSupportedTimezones(): string[] {
  const intlWithValues = Intl as typeof Intl & {
    supportedValuesOf?: (key: "timeZone") => string[];
  };
  return intlWithValues.supportedValuesOf?.("timeZone") ?? fallbackTimezones;
}

interface TimezonePickerProps {
  id: string;
  value: string;
  onChange: (value: string) => void;
}

export function TimezonePicker({ id, value, onChange }: TimezonePickerProps) {
  const timezones = useMemo(getSupportedTimezones, []);
  const now = useMemo(
    () =>
      new Intl.DateTimeFormat(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        timeZone: value || "UTC",
        timeZoneName: "short",
      }).format(new Date()),
    [value],
  );

  return (
    <div className="space-y-2">
      <Input
        id={id}
        list="timezone-options"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <datalist id="timezone-options">
        {timezones.map((timezone) => (
          <option key={timezone} value={timezone} />
        ))}
      </datalist>
      <p className="text-xs text-muted-foreground">Current local time: {now}</p>
    </div>
  );
}
