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
