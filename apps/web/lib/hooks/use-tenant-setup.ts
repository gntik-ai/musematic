"use client";

import { createApiClient } from "@/lib/api";
import { useAppMutation, useAppQuery } from "@/lib/hooks/use-api";

const setupApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

const SETUP_OPTIONS = {
  credentials: "include" as const,
  skipAuth: true,
  skipRetry: true,
};

export type SetupStep = "tos" | "credentials" | "mfa" | "workspace" | "invitations" | "done";

export interface TenantSetupValidationResponse {
  invitation_id?: string;
  tenant_id: string;
  tenant_slug: string;
  tenant_display_name: string;
  target_email: string;
  expires_at: string;
  current_step: SetupStep;
  completed_steps: string[];
  mfa_required?: boolean;
}

export interface SetupTosPayload {
  tos_version: string;
  accepted_at_ts: string;
}

export type SetupCredentialsPayload =
  | {
      method: "password";
      password: string;
    }
  | {
      method: "oauth";
      provider: string;
      oauth_token: string;
    };

export interface SetupMfaStartResponse {
  totp_secret: string;
  provisioning_uri: string;
  recovery_codes_to_generate_count: number;
}

export interface SetupMfaVerifyPayload {
  totp_code: string;
}

export interface SetupMfaVerifyResponse {
  next_step: SetupStep;
  recovery_codes: string[];
}

export interface SetupWorkspacePayload {
  name: string;
}

export interface SetupInvitationsPayload {
  invitations: Array<{
    email: string;
    role?: string;
    message?: string | null;
  }>;
}

export interface SetupNextStepResponse {
  next_step: SetupStep;
  [key: string]: unknown;
}

export interface SetupCompleteResponse {
  redirect_to: string;
}

export const tenantSetupQueryKeys = {
  validate: (token: string) => ["tenant-setup", "validate", token] as const,
};

export function useTenantSetup(token: string) {
  return useAppQuery(
    tenantSetupQueryKeys.validate(token),
    () => validateSetupToken(token),
    {
      enabled: token.length > 0,
      retry: false,
    },
  );
}

export function useTenantSetupMutations() {
  return {
    complete: useAppMutation(completeSetup),
    credentials: useAppMutation(submitCredentials),
    invitations: useAppMutation(submitInvitations),
    mfaStart: useAppMutation(startMfa),
    mfaVerify: useAppMutation(verifyMfa),
    tos: useAppMutation(submitTos),
    workspace: useAppMutation(submitWorkspace),
  };
}

async function validateSetupToken(token: string): Promise<TenantSetupValidationResponse> {
  const query = new URLSearchParams({ token });
  return setupApi.post<TenantSetupValidationResponse>(
    `/api/v1/setup/validate-token?${query.toString()}`,
    undefined,
    SETUP_OPTIONS,
  );
}

async function submitTos(payload: SetupTosPayload): Promise<SetupNextStepResponse> {
  return setupApi.post<SetupNextStepResponse>("/api/v1/setup/step/tos", payload, SETUP_OPTIONS);
}

async function submitCredentials(
  payload: SetupCredentialsPayload,
): Promise<SetupNextStepResponse> {
  return setupApi.post<SetupNextStepResponse>(
    "/api/v1/setup/step/credentials",
    payload,
    SETUP_OPTIONS,
  );
}

async function startMfa(): Promise<SetupMfaStartResponse> {
  return setupApi.post<SetupMfaStartResponse>(
    "/api/v1/setup/step/mfa/start",
    undefined,
    SETUP_OPTIONS,
  );
}

async function verifyMfa(payload: SetupMfaVerifyPayload): Promise<SetupMfaVerifyResponse> {
  return setupApi.post<SetupMfaVerifyResponse>(
    "/api/v1/setup/step/mfa/verify",
    payload,
    SETUP_OPTIONS,
  );
}

async function submitWorkspace(payload: SetupWorkspacePayload): Promise<SetupNextStepResponse> {
  return setupApi.post<SetupNextStepResponse>(
    "/api/v1/setup/step/workspace",
    payload,
    SETUP_OPTIONS,
  );
}

async function submitInvitations(
  payload: SetupInvitationsPayload,
): Promise<SetupNextStepResponse> {
  return setupApi.post<SetupNextStepResponse>(
    "/api/v1/setup/step/invitations",
    payload,
    SETUP_OPTIONS,
  );
}

async function completeSetup(): Promise<SetupCompleteResponse> {
  return setupApi.post<SetupCompleteResponse>(
    "/api/v1/setup/complete",
    undefined,
    SETUP_OPTIONS,
  );
}
