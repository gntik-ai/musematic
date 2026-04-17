"use client";

import { createApiClient } from "@/lib/api";
import type { ApiError } from "@/types/api";
import type { AuthSession, RoleType, UserProfile } from "@/types/auth";

const authApi = createApiClient(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");

export interface AuthUserResponse {
  id: string;
  email: string;
  display_name: string;
  avatar_url: string | null;
  roles: RoleType[];
  workspace_id: string | null;
  mfa_enrolled: boolean;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginSuccessResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: AuthUserResponse;
}

export interface MfaChallengeResponse {
  mfa_required: true;
  session_token: string;
}

export type LoginResponse = LoginSuccessResponse | MfaChallengeResponse;

export interface LockoutErrorResponse {
  code: "ACCOUNT_LOCKED";
  lockout_seconds: number;
}

export interface MfaVerifyRequest {
  session_token: string;
  code: string;
  use_recovery_code?: boolean | undefined;
}

export interface MfaVerifyResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: AuthUserResponse;
  recovery_code_consumed?: boolean;
}

export interface PasswordResetRequestBody {
  email: string;
}

export interface PasswordResetCompleteRequest {
  token: string;
  new_password: string;
}

export interface PasswordResetCompleteResponse {
  success: true;
}

export interface PasswordResetTokenErrorResponse {
  code: "TOKEN_EXPIRED" | "TOKEN_ALREADY_USED";
}

export interface MfaEnrollResponse {
  provisioning_uri: string;
  secret_key: string;
}

export interface MfaConfirmRequest {
  code: string;
}

export interface MfaConfirmResponse {
  recovery_codes: string[];
}

export async function login(request: LoginRequest): Promise<LoginResponse> {
  return authApi.post<LoginResponse>("/api/v1/auth/login", request, {
    skipAuth: true,
    skipRetry: true,
  });
}

export async function verifyMfa(request: MfaVerifyRequest): Promise<MfaVerifyResponse> {
  return authApi.post<MfaVerifyResponse>("/api/v1/auth/mfa/verify", request, {
    skipAuth: true,
    skipRetry: true,
  });
}

export async function requestPasswordReset(
  request: PasswordResetRequestBody,
): Promise<void> {
  await authApi.post<void>("/api/v1/password-reset/request", request, {
    skipAuth: true,
    skipRetry: true,
  });
}

export async function completePasswordReset(
  request: PasswordResetCompleteRequest,
): Promise<PasswordResetCompleteResponse> {
  return authApi.post<PasswordResetCompleteResponse>(
    "/api/v1/password-reset/complete",
    request,
    {
      skipAuth: true,
      skipRetry: true,
    },
  );
}

export async function enrollMfa(): Promise<MfaEnrollResponse> {
  return authApi.post<MfaEnrollResponse>("/api/v1/auth/mfa/enroll", undefined, {
    skipRetry: true,
  });
}

export async function confirmMfa(request: MfaConfirmRequest): Promise<MfaConfirmResponse> {
  return authApi.post<MfaConfirmResponse>("/api/v1/auth/mfa/confirm", request, {
    skipRetry: true,
  });
}

export function isMfaChallengeResponse(response: LoginResponse): response is MfaChallengeResponse {
  return "mfa_required" in response && response.mfa_required === true;
}

export function toUserProfile(user: AuthUserResponse): UserProfile {
  return {
    id: user.id,
    email: user.email,
    displayName: user.display_name,
    avatarUrl: user.avatar_url,
    roles: user.roles,
    workspaceId: user.workspace_id,
    mfaEnrolled: user.mfa_enrolled,
  };
}

export function toAuthSession(
  response: LoginSuccessResponse | MfaVerifyResponse,
): AuthSession {
  return {
    accessToken: response.access_token,
    refreshToken: response.refresh_token,
    expiresIn: response.expires_in,
    user: toUserProfile(response.user),
  };
}

export function getLockoutSeconds(error: ApiError): number | null {
  const lockoutSeconds = error.meta?.lockout_seconds;
  return typeof lockoutSeconds === "number" ? lockoutSeconds : null;
}
