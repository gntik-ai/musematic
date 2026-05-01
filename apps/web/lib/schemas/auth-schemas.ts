"use client";

import { z } from "zod";

export const PASSWORD_RULES = [
  {
    key: "length",
    label: "Minimum 12 characters",
    test: (value: string) => value.length >= 12,
  },
  {
    key: "uppercase",
    label: "Uppercase letter",
    test: (value: string) => /[A-Z]/.test(value),
  },
  {
    key: "lowercase",
    label: "Lowercase letter",
    test: (value: string) => /[a-z]/.test(value),
  },
  {
    key: "digit",
    label: "One digit",
    test: (value: string) => /[0-9]/.test(value),
  },
  {
    key: "special",
    label: "Special character",
    test: (value: string) => /[^A-Za-z0-9]/.test(value),
  },
] as const;

export const loginSchema = z.object({
  email: z.string().email("Enter a valid email address"),
  password: z.string().min(1, "Password is required"),
});

export const forgotPasswordSchema = z.object({
  email: z.string().email("Enter a valid email address"),
});

const passwordSchema = z
  .string()
  .min(12, "Minimum 12 characters")
  .regex(/[A-Z]/, "At least one uppercase letter")
  .regex(/[a-z]/, "At least one lowercase letter")
  .regex(/[0-9]/, "At least one digit")
  .regex(/[^A-Za-z0-9]/, "At least one special character");

export const resetPasswordSchema = z
  .object({
    newPassword: passwordSchema,
    confirmPassword: z.string(),
  })
  .refine((value) => value.newPassword === value.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });

export const signupSchema = z
  .object({
    email: z.string().email("Enter a valid email address"),
    displayName: z.string().min(2, "Display name is required").max(100),
    password: passwordSchema,
    aiDisclosureAccepted: z
      .boolean()
      .refine((value) => value, "AI disclosure consent is required"),
    termsAccepted: z
      .boolean()
      .refine((value) => value, "Terms acceptance is required"),
  });

export const profileCompletionSchema = z.object({
  displayName: z.string().min(2, "Display name is required").max(100),
  locale: z.enum(["en", "es", "fr", "de", "it", "ja", "zh-CN"]),
  timezone: z.string().min(1, "Timezone is required").max(64),
});

export const mfaCodeSchema = z.object({
  code: z.string().regex(/^\d{6}$/, "Enter a 6-digit code"),
  useRecoveryCode: z.literal(false).default(false),
});

export const recoveryCodeSchema = z.object({
  code: z.string().min(1, "Recovery code is required"),
  useRecoveryCode: z.literal(true),
});

export const mfaInputSchema = z.discriminatedUnion("useRecoveryCode", [
  mfaCodeSchema,
  recoveryCodeSchema,
]);

export function evaluatePasswordRules(password: string): Array<{
  key: (typeof PASSWORD_RULES)[number]["key"];
  label: string;
  satisfied: boolean;
}> {
  return PASSWORD_RULES.map((rule) => ({
    key: rule.key,
    label: rule.label,
    satisfied: rule.test(password),
  }));
}

export type LoginFormValues = z.infer<typeof loginSchema>;
export type ForgotPasswordFormValues = z.infer<typeof forgotPasswordSchema>;
export type ResetPasswordFormValues = z.infer<typeof resetPasswordSchema>;
export type SignupFormValues = z.infer<typeof signupSchema>;
export type ProfileCompletionFormValues = z.infer<typeof profileCompletionSchema>;
export type MfaCodeFormValues = z.infer<typeof mfaCodeSchema>;
export type RecoveryCodeFormValues = z.infer<typeof recoveryCodeSchema>;
export type MfaInputFormValues = z.infer<typeof mfaInputSchema>;
