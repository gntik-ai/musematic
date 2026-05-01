"use client";

import { z } from "zod";

export const themeValues = ["light", "dark", "system", "high_contrast"] as const;
export const localeValues = ["en", "es", "fr", "de", "it", "ja", "zh-CN"] as const;
export const dataExportFormats = ["json", "csv", "ndjson"] as const;

export const notificationPreferencesSchema = z.object({
  email: z.boolean(),
  in_app: z.boolean(),
  mobile_push: z.boolean(),
  quiet_hours_start: z.string(),
  quiet_hours_end: z.string(),
});

export const preferencesFormSchema = z.object({
  theme: z.enum(themeValues),
  language: z.enum(localeValues),
  timezone: z.string().min(1, "Select a time zone"),
  default_workspace_id: z
    .string()
    .uuid("Select a workspace from the list")
    .nullable(),
  data_export_format: z.enum(dataExportFormats),
  notification_preferences: notificationPreferencesSchema,
});

export type PreferencesFormValues = z.infer<typeof preferencesFormSchema>;

export const defaultNotificationPreferences: PreferencesFormValues["notification_preferences"] = {
  email: true,
  in_app: true,
  mobile_push: false,
  quiet_hours_start: "22:00",
  quiet_hours_end: "07:00",
};
