"use client";

import { Contrast, Laptop, MoonStar, SunMedium } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ThemePreference } from "@/lib/api/preferences";

export const themeOptions = [
  { value: "light", label: "Light", description: "Bright interface", icon: SunMedium },
  { value: "dark", label: "Dark", description: "Reduced glare", icon: MoonStar },
  { value: "system", label: "System", description: "Follow OS", icon: Laptop },
  { value: "high_contrast", label: "High contrast", description: "Maximum contrast", icon: Contrast },
] satisfies Array<{
  value: ThemePreference;
  label: string;
  description: string;
  icon: typeof SunMedium;
}>;

interface ThemePickerProps {
  value: ThemePreference;
  onChange: (theme: ThemePreference) => void;
}

export function ThemePicker({ value, onChange }: ThemePickerProps) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" role="radiogroup" aria-label="Theme">
      {themeOptions.map((option) => {
        const Icon = option.icon;
        const selected = value === option.value;
        return (
          <button
            key={option.value}
            aria-checked={selected}
            className={cn(
              "flex min-h-24 flex-col items-start justify-between rounded-lg border border-border bg-background p-3 text-left transition-colors hover:bg-accent",
              selected && "border-primary ring-2 ring-ring",
            )}
            data-testid={`theme-picker-${option.value}`}
            role="radio"
            type="button"
            onClick={() => onChange(option.value)}
          >
            <Icon className="h-5 w-5 text-brand-accent" />
            <span>
              <span className="block text-sm font-semibold">{option.label}</span>
              <span className="block text-xs text-muted-foreground">{option.description}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
