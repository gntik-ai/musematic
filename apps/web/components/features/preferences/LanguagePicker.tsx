"use client";

import { Select } from "@/components/ui/select";

export const localeOptions = [
  { value: "en", label: "English" },
  { value: "es", label: "Español" },
  { value: "fr", label: "Français" },
  { value: "de", label: "Deutsch" },
  { value: "ja", label: "日本語" },
  { value: "zh-CN", label: "简体中文" },
] as const;

interface LanguagePickerProps {
  id: string;
  value: string;
  onChange: (value: string) => void;
}

export function LanguagePicker({ id, value, onChange }: LanguagePickerProps) {
  return (
    <Select id={id} value={value} onChange={(event) => onChange(event.target.value)}>
      {localeOptions.map((locale) => (
        <option key={locale.value} value={locale.value}>
          {locale.label}
        </option>
      ))}
    </Select>
  );
}
