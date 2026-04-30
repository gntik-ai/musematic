import { z } from "zod";

export const oauthProviderAdminSchema = z.object({
  client_id: z.string().trim().min(1, "Client ID is required"),
  client_secret_ref: z.string().trim().min(1, "Client secret reference is required"),
  default_role: z.string().trim().min(1, "Default role is required"),
  display_name: z.string().trim().min(1, "Display name is required"),
  domain_restrictions_text: z.string(),
  enabled: z.boolean(),
  group_role_mapping_text: z
    .string()
    .refine(
      (value) =>
        value
          .split(/\r?\n/)
          .map((line) => line.trim())
          .filter(Boolean)
          .every((line) => line.includes("=")),
      "Use one mapping per line in the format group=role",
    ),
  org_restrictions_text: z.string(),
  redirect_uri: z.string().trim().url("Enter a valid redirect URI"),
  require_mfa: z.boolean(),
  scopes_text: z.string().trim().min(1, "Enter at least one scope"),
});

export type OAuthProviderAdminFormValues = z.infer<typeof oauthProviderAdminSchema>;

export const oauthSecretRotateSchema = z.object({
  new_secret: z.string().trim().min(1, "Secret is required"),
});

export const oauthConfigReseedSchema = z.object({
  force_update: z.boolean().default(false),
});

export const oauthRateLimitConfigSchema = z.object({
  per_ip_max: z.coerce.number().int().min(1, "Per-IP limit must be at least 1"),
  per_ip_window: z.coerce.number().int().min(1, "Per-IP window must be at least 1"),
  per_user_max: z.coerce.number().int().min(1, "Per-user limit must be at least 1"),
  per_user_window: z.coerce.number().int().min(1, "Per-user window must be at least 1"),
  global_max: z.coerce.number().int().min(1, "Global limit must be at least 1"),
  global_window: z.coerce.number().int().min(1, "Global window must be at least 1"),
});

export const oauthHistoryEntrySchema = z.object({
  timestamp: z.string(),
  admin_id: z.string().nullable(),
  action: z.string(),
  before: z.record(z.unknown()).nullable(),
  after: z.record(z.unknown()).nullable(),
});

export const oauthHistoryListSchema = z.object({
  entries: z.array(oauthHistoryEntrySchema),
  next_cursor: z.string().nullable(),
});

export const oauthConnectivityTestSchema = z.object({
  reachable: z.boolean(),
  auth_url_returned: z.boolean(),
  diagnostic: z.string(),
});

export const oauthConfigReseedResponseSchema = z.object({
  diff: z.record(z.unknown()),
});

export type OAuthSecretRotateValues = z.infer<typeof oauthSecretRotateSchema>;
export type OAuthConfigReseedValues = z.infer<typeof oauthConfigReseedSchema>;
export type OAuthRateLimitConfigValues = z.infer<typeof oauthRateLimitConfigSchema>;
