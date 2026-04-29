"use client";

import { useMemo } from "react";
import { Contrast, Laptop, MoonStar, SunMedium } from "lucide-react";
import { useTheme } from "next-themes";
import { useUpdatePreferences, type ThemePreference } from "@/lib/api/preferences";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { toast } from "@/lib/hooks/use-toast";

const THEME_COOKIE = "musematic-theme";

const THEMES = [
  { value: "light", label: "Light", icon: SunMedium },
  { value: "dark", label: "Dark", icon: MoonStar },
  { value: "system", label: "System", icon: Laptop },
  { value: "high_contrast", label: "High contrast", icon: Contrast },
] satisfies Array<{
  value: ThemePreference;
  label: string;
  icon: typeof SunMedium;
}>;
const SYSTEM_THEME = THEMES[2]!;

function setThemeCookie(theme: ThemePreference) {
  document.cookie = `${THEME_COOKIE}=${theme}; Path=/; SameSite=Lax`;
}

export function ThemeToggle() {
  const { theme, resolvedTheme, setTheme } = useTheme();
  const updatePreferences = useUpdatePreferences();
  const activeTheme = (theme ?? "system") as ThemePreference;
  const active = useMemo(
    () => THEMES.find((item) => item.value === activeTheme) ?? SYSTEM_THEME,
    [activeTheme],
  );
  const ActiveIcon = active.icon;

  async function selectTheme(nextTheme: ThemePreference) {
    const previousTheme = (theme ?? "system") as ThemePreference;
    setTheme(nextTheme);
    setThemeCookie(nextTheme);
    try {
      await updatePreferences.mutateAsync({ theme: nextTheme });
    } catch (error) {
      setTheme(previousTheme);
      setThemeCookie(previousTheme);
      toast({
        title: "Theme was not saved",
        description: error instanceof Error ? error.message : "Try again.",
        variant: "destructive",
      });
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          aria-label={`Theme: ${active.label}`}
          data-testid="theme-toggle"
          size="icon"
          title={`Theme: ${active.label}`}
          variant="ghost"
        >
          <ActiveIcon className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52">
        <DropdownMenuLabel>Theme</DropdownMenuLabel>
        {THEMES.map((item) => {
          const Icon = item.icon;
          const selected = item.value === activeTheme || (item.value !== "system" && item.value === resolvedTheme);
          return (
            <DropdownMenuItem
              key={item.value}
              aria-checked={selected}
              data-testid={`theme-option-${item.value}`}
              role="menuitemradio"
              onClick={() => {
                void selectTheme(item.value);
              }}
            >
              <Icon className="h-4 w-4" />
              <span>{item.label}</span>
              {selected ? <span className="ml-auto text-xs text-muted-foreground">Active</span> : null}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
