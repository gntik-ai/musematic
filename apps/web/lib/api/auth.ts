"use client";

import { createApiClient } from "@/lib/api";
import type {
  OAuthAuthorizeResponse,
  OAuthLinkListResponse,
  OAuthProviderAdminListResponse,
  OAuthProviderAdminResponse,
  OAuthProviderPublicListResponse,
  OAuthProviderType,
  OAuthProviderUpsertRequest,
} from "@/lib/types/oauth";
import type { ApiError } from "@/types/api";
import type { AccountStatus, AuthSession, RoleType, UserProfile } from "@/types/auth";

const authApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export interface AuthUserResponse {
  id: string;
  email: string;
  display_name: string;
  avatar_url: string | null;
  roles: RoleType[];
  workspace_id: string | null;
  mfa_enrolled: boolean;
  status?: AccountStatus;
  has_local_password?: boolean;
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

export interface OAuthCallbackSuccessResponse {
  token_pair: {
    access_token: string;
    refresh_token: string;
    expires_in: number;
  };
  user: AuthUserResponse;
  recovery_intent?: boolean;
}

export interface OAuthCallbackMfaResponse {
  mfa_required: true;
  session_token: string;
  user: AuthUserResponse;
}

export type OAuthCallbackResponse =
  | OAuthCallbackSuccessResponse
  | OAuthCallbackMfaResponse;

export interface RegisterRequest {
  email: string;
  display_name: string;
  password: string;
}

export interface RegisterResponse {
  message: string;
}

export interface VerifyEmailResponse {
  user_id: string;
  status: AccountStatus;
}

export interface ResendVerificationResponse {
  message: string;
}

export interface ProfileUpdateRequest {
  locale?: string;
  timezone?: string;
  display_name?: string;
}

export interface ProfileUpdateResponse {
  user_id: string;
  email: string;
  display_name: string;
  status: AccountStatus;
  locale: string | null;
  timezone: string | null;
}

export async function login(request: LoginRequest): Promise<LoginResponse> {
  return authApi.post<LoginResponse>("/api/v1/auth/login", request, {
    skipAuth: true,
    skipRetry: true,
  });
}

export async function verifyMfa(
  request: MfaVerifyRequest,
): Promise<MfaVerifyResponse> {
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

export async function confirmMfa(
  request: MfaConfirmRequest,
): Promise<MfaConfirmResponse> {
  return authApi.post<MfaConfirmResponse>("/api/v1/auth/mfa/confirm", request, {
    skipRetry: true,
  });
}

export async function listOAuthProviders(): Promise<OAuthProviderPublicListResponse> {
  return authApi.get<OAuthProviderPublicListResponse>("/api/v1/auth/oauth/providers", {
    skipAuth: true,
  });
}

export async function listOAuthLinks(): Promise<OAuthLinkListResponse> {
  return authApi.get<OAuthLinkListResponse>("/api/v1/auth/oauth/links");
}

export async function listOAuthLinkStatus(
  email: string,
): Promise<OAuthLinkListResponse> {
  return authApi.get<OAuthLinkListResponse>(
    `/api/v1/auth/oauth/links?email=${encodeURIComponent(email)}`,
    {
      skipAuth: true,
      skipRetry: true,
    },
  );
}

export async function authorizeOAuthProvider(
  providerType: OAuthProviderType,
): Promise<OAuthAuthorizeResponse> {
  return authApi.get<OAuthAuthorizeResponse>(
    `/api/v1/auth/oauth/${providerType}/authorize`,
    { skipAuth: true },
  );
}

export async function recoverWithOAuthProvider(
  providerType: OAuthProviderType,
  email: string,
): Promise<OAuthAuthorizeResponse> {
  const query = new URLSearchParams({
    email,
    intent: "recovery",
  });

  return authApi.get<OAuthAuthorizeResponse>(
    `/api/v1/auth/oauth/${providerType}/authorize?${query.toString()}`,
    { skipAuth: true },
  );
}

export async function linkOAuthProvider(
  providerType: OAuthProviderType,
): Promise<OAuthAuthorizeResponse> {
  return authApi.post<OAuthAuthorizeResponse>(
    `/api/v1/auth/oauth/${providerType}/link`,
  );
}

export async function unlinkOAuthProvider(
  providerType: OAuthProviderType,
): Promise<void> {
  return authApi.delete<void>(`/api/v1/auth/oauth/${providerType}/link`);
}

export async function register(payload: RegisterRequest): Promise<RegisterResponse> {
  return authApi.post<RegisterResponse>("/api/v1/accounts/register", payload, {
    skipAuth: true,
    skipRetry: true,
  });
}

export async function verifyEmail(token: string): Promise<VerifyEmailResponse> {
  return authApi.post<VerifyEmailResponse>(
    "/api/v1/accounts/verify-email",
    { token },
    {
      skipAuth: true,
      skipRetry: true,
    },
  );
}

export async function resendVerification(
  email: string,
): Promise<ResendVerificationResponse> {
  return authApi.post<ResendVerificationResponse>(
    "/api/v1/accounts/resend-verification",
    { email },
    {
      skipAuth: true,
      skipRetry: true,
    },
  );
}

export async function getCurrentAccount(): Promise<ProfileUpdateResponse> {
  return authApi.get<ProfileUpdateResponse>("/api/v1/accounts/me", {
    skipRetry: true,
  });
}

export async function updateProfile(
  payload: ProfileUpdateRequest,
): Promise<ProfileUpdateResponse> {
  return authApi.patch<ProfileUpdateResponse>("/api/v1/accounts/me", payload, {
    skipRetry: true,
  });
}

export async function listAdminOAuthProviders(): Promise<OAuthProviderAdminListResponse> {
  return authApi.get<OAuthProviderAdminListResponse>("/api/v1/admin/oauth/providers");
}

export async function upsertAdminOAuthProvider(
  providerType: OAuthProviderType,
  payload: OAuthProviderUpsertRequest,
): Promise<OAuthProviderAdminResponse> {
  return authApi.put<OAuthProviderAdminResponse>(
    `/api/v1/admin/oauth/providers/${providerType}`,
    payload,
  );
}

export function isMfaChallengeResponse(
  response: LoginResponse,
): response is MfaChallengeResponse {
  return "mfa_required" in response && response.mfa_required === true;
}

export function isOAuthCallbackMfaResponse(
  response: OAuthCallbackResponse,
): response is OAuthCallbackMfaResponse {
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
    status: user.status ?? "active",
    hasLocalPassword: user.has_local_password ?? true,
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

export function toAuthSessionFromOAuthCallback(
  response: OAuthCallbackSuccessResponse,
): AuthSession {
  return {
    accessToken: response.token_pair.access_token,
    refreshToken: response.token_pair.refresh_token,
    expiresIn: response.token_pair.expires_in,
    user: toUserProfile(response.user),
  };
}

export function decodeOAuthSessionFragment(
  encodedFragment: string,
): OAuthCallbackResponse {
  const normalized = encodedFragment.replace(/-/g, "+").replace(/_/g, "/");
  const padding = (4 - (normalized.length % 4)) % 4;
  const decoded = window.atob(normalized.padEnd(normalized.length + padding, "="));
  return JSON.parse(decoded) as OAuthCallbackResponse;
}

export function getLockoutSeconds(error: ApiError): number | null {
  const lockoutSeconds = error.meta?.lockout_seconds;
  return typeof lockoutSeconds === "number" ? lockoutSeconds : null;
}
