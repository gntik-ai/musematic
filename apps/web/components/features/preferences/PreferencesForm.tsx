"use client";

import { useEffect } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { Save } from "lucide-react";
import { useTheme } from "next-themes";
import { useForm } from "react-hook-form";
import {
  useUpdatePreferences,
  useUserPreferences,
  type ThemePreference,
} from "@/lib/api/preferences";
import { useWorkspaces } from "@/lib/hooks/use-workspaces";
import { toast } from "@/lib/hooks/use-toast";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { LanguagePicker } from "@/components/features/preferences/LanguagePicker";
import { NotificationPreferencesSection } from "@/components/features/preferences/NotificationPreferencesSection";
import { ThemePicker } from "@/components/features/preferences/ThemePicker";
import { TimezonePicker } from "@/components/features/preferences/TimezonePicker";
import {
  dataExportFormats,
  defaultNotificationPreferences,
  preferencesFormSchema,
  type PreferencesFormValues,
} from "@/components/features/preferences/preferences-schema";

const THEME_COOKIE = "musematic-theme";

const defaultValues: PreferencesFormValues = {
  theme: "system",
  language: "en",
  timezone: "UTC",
  default_workspace_id: null,
  data_export_format: "json",
  notification_preferences: defaultNotificationPreferences,
};

function normalizeNotificationPreferences(value: Record<string, unknown>): PreferencesFormValues["notification_preferences"] {
  return {
    ...defaultNotificationPreferences,
    ...value,
  };
}

function persistTheme(theme: ThemePreference) {
  document.cookie = `${THEME_COOKIE}=${theme}; Path=/; SameSite=Lax`;
}

export function PreferencesForm() {
  const preferences = useUserPreferences();
  const updatePreferences = useUpdatePreferences();
  const { workspaces } = useWorkspaces();
  const { setTheme } = useTheme();
  const form = useForm<PreferencesFormValues>({
    resolver: zodResolver(preferencesFormSchema),
    defaultValues,
  });

  useEffect(() => {
    if (!preferences.data) {
      return;
    }
    form.reset({
      theme: preferences.data.theme,
      language: preferences.data.language as PreferencesFormValues["language"],
      timezone: preferences.data.timezone,
      default_workspace_id: preferences.data.default_workspace_id,
      data_export_format: preferences.data.data_export_format,
      notification_preferences: normalizeNotificationPreferences(
        preferences.data.notification_preferences,
      ),
    });
  }, [form, preferences.data]);

  const notificationPreferences = form.watch("notification_preferences");
  const selectedTheme = form.watch("theme");

  async function onSubmit(values: PreferencesFormValues) {
    try {
      await updatePreferences.mutateAsync(values);
      setTheme(values.theme);
      persistTheme(values.theme);
      toast({
        title: "Preferences saved",
        variant: "success",
      });
    } catch (error) {
      toast({
        title: "Preferences were not saved",
        description: error instanceof Error ? error.message : "Try again.",
        variant: "destructive",
      });
    }
  }

  return (
    <form className="space-y-5" onSubmit={form.handleSubmit(onSubmit)}>
      <Card>
        <CardHeader>
          <CardTitle>Display</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <ThemePicker
            value={selectedTheme}
            onChange={(theme) => form.setValue("theme", theme, { shouldDirty: true })}
          />
          {form.formState.errors.theme ? (
            <p className="text-sm text-destructive" role="alert">
              {form.formState.errors.theme.message}
            </p>
          ) : null}
          <div className="grid gap-4 md:grid-cols-2">
            <div id="language" className="space-y-2">
              <Label htmlFor="language-select">Language</Label>
              <LanguagePicker
                id="language-select"
                value={form.watch("language")}
                onChange={(language) =>
                  form.setValue("language", language as PreferencesFormValues["language"], {
                    shouldDirty: true,
                  })
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="timezone-select">Time zone</Label>
              <TimezonePicker
                id="timezone-select"
                value={form.watch("timezone")}
                onChange={(timezone) => form.setValue("timezone", timezone, { shouldDirty: true })}
              />
              {form.formState.errors.timezone ? (
                <p className="text-sm text-destructive" role="alert">
                  {form.formState.errors.timezone.message}
                </p>
              ) : null}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Workspace and exports</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="default-workspace">Default workspace</Label>
            <Select
              id="default-workspace"
              value={form.watch("default_workspace_id") ?? ""}
              onChange={(event) =>
                form.setValue("default_workspace_id", event.target.value || null, {
                  shouldDirty: true,
                })
              }
            >
              <option value="">No default workspace</option>
              {workspaces.map((workspace) => (
                <option key={workspace.id} value={workspace.id}>
                  {workspace.name}
                </option>
              ))}
            </Select>
            {form.formState.errors.default_workspace_id ? (
              <p className="text-sm text-destructive" role="alert">
                {form.formState.errors.default_workspace_id.message}
              </p>
            ) : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="data-export-format">Data export format</Label>
            <Select
              id="data-export-format"
              value={form.watch("data_export_format")}
              onChange={(event) =>
                form.setValue(
                  "data_export_format",
                  event.target.value as PreferencesFormValues["data_export_format"],
                  { shouldDirty: true },
                )
              }
            >
              {dataExportFormats.map((format) => (
                <option key={format} value={format}>
                  {format.toUpperCase()}
                </option>
              ))}
            </Select>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <NotificationPreferencesSection
            value={notificationPreferences}
            onChange={(value) =>
              form.setValue("notification_preferences", value, { shouldDirty: true })
            }
          />
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button disabled={updatePreferences.isPending} type="submit">
          <Save className="h-4 w-4" />
          {updatePreferences.isPending ? "Saving..." : "Save preferences"}
        </Button>
      </div>
    </form>
  );
}
