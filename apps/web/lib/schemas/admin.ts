import { z } from "zod";

const emptyStringToNull = (value: unknown): unknown => {
  if (value === "" || value === undefined) {
    return null;
  }

  return value;
};

const positiveIntegerField = (minimum: number, maximum?: number) => {
  let schema = z.coerce.number().int().min(minimum);
  if (maximum !== undefined) {
    schema = schema.max(maximum);
  }
  return schema;
};

const nullableIntegerField = (minimum: number, maximum?: number) => {
  let schema = z.coerce.number().int().min(minimum);
  if (maximum !== undefined) {
    schema = schema.max(maximum);
  }

  return z.preprocess(emptyStringToNull, schema.nullable());
};

const optionalCredential = z.union([z.string().trim().min(1), z.literal("")]).optional();

export const signupPolicySchema = z.object({
  signup_mode: z.enum(["open", "invite_only", "admin_approval"]),
  mfa_enforcement: z.enum(["optional", "required"]),
});

export const defaultQuotasSchema = z.object({
  max_agents: positiveIntegerField(1, 10_000),
  max_concurrent_executions: positiveIntegerField(1, 1_000),
  max_sandboxes: positiveIntegerField(0, 500),
  monthly_token_budget: positiveIntegerField(0),
  storage_quota_gb: positiveIntegerField(1, 10_000),
});

export const workspaceQuotaOverrideSchema = z.object({
  max_agents: nullableIntegerField(1, 10_000),
  max_concurrent_executions: nullableIntegerField(1, 1_000),
  max_sandboxes: nullableIntegerField(0, 500),
  monthly_token_budget: nullableIntegerField(0),
  storage_quota_gb: nullableIntegerField(1, 10_000),
});

export const emailSmtpSchema = z.object({
  mode: z.literal("smtp"),
  host: z.string().trim().min(1, "Host is required"),
  port: positiveIntegerField(1, 65535),
  username: z.string().trim().min(1, "Username is required"),
  new_password: optionalCredential,
  encryption: z.enum(["tls", "starttls", "none"]),
  from_address: z.string().trim().email("Valid email required"),
  from_name: z.string().trim().min(1, "From name is required"),
});

export const emailSesSchema = z.object({
  mode: z.literal("ses"),
  region: z.string().trim().min(1, "Region is required"),
  access_key_id: z.string().trim().min(1, "Access key ID is required"),
  new_secret_access_key: optionalCredential,
  from_address: z.string().trim().email("Valid email required"),
  from_name: z.string().trim().min(1, "From name is required"),
});

export const emailConfigSchema = z.discriminatedUnion("mode", [
  emailSmtpSchema,
  emailSesSchema,
]);

export const securityPolicySchema = z.object({
  password_min_length: z.coerce
    .number()
    .int()
    .min(8, "Minimum 8 characters")
    .max(128),
  password_require_uppercase: z.boolean(),
  password_require_lowercase: z.boolean(),
  password_require_digit: z.boolean(),
  password_require_special: z.boolean(),
  password_expiry_days: z.preprocess(
    emptyStringToNull,
    z.coerce.number().int().min(1).max(365).nullable(),
  ),
  session_duration_minutes: z.coerce
    .number()
    .int()
    .min(15, "Minimum 15 minutes")
    .max(43_200, "Maximum 30 days"),
  lockout_max_attempts: z.coerce
    .number()
    .int()
    .min(1, "Minimum 1 attempt")
    .max(20, "Maximum 20 attempts"),
  lockout_duration_minutes: z.coerce
    .number()
    .int()
    .min(1)
    .max(1_440, "Maximum 24 hours"),
});

export const testEmailSchema = z.object({
  recipient: z.string().trim().email("Valid email address required"),
});
