"use client";

import { useMutation, type UseMutationResult } from "@tanstack/react-query";
import {
  completePasswordReset,
  confirmMfa,
  disableMfa,
  enrollMfa,
  login,
  regenerateMfaRecoveryCodes,
  requestPasswordReset,
  resendVerification,
  register,
  updateProfile,
  verifyEmail,
  verifyMfa,
  type LoginRequest,
  type LoginResponse,
  type MfaConfirmRequest,
  type MfaConfirmResponse,
  type MfaDisableRequest,
  type MfaDisableResponse,
  type MfaEnrollResponse,
  type MfaRecoveryCodesRegenerateRequest,
  type MfaRecoveryCodesRegenerateResponse,
  type MfaVerifyRequest,
  type MfaVerifyResponse,
  type PasswordResetCompleteRequest,
  type PasswordResetCompleteResponse,
  type PasswordResetRequestBody,
  type ProfileUpdateRequest,
  type ProfileUpdateResponse,
  type RegisterRequest,
  type RegisterResponse,
  type ResendVerificationResponse,
  type VerifyEmailResponse,
} from "@/lib/api/auth";
import type { ApiError } from "@/types/api";

export function useLoginMutation(): UseMutationResult<
  LoginResponse,
  ApiError,
  LoginRequest
> {
  return useMutation({
    mutationFn: login,
  });
}

export function useMfaVerifyMutation(): UseMutationResult<
  MfaVerifyResponse,
  ApiError,
  MfaVerifyRequest
> {
  return useMutation({
    mutationFn: verifyMfa,
  });
}

export function useForgotPasswordMutation(): UseMutationResult<
  void,
  ApiError,
  PasswordResetRequestBody
> {
  return useMutation({
    mutationFn: requestPasswordReset,
  });
}

export function useRegisterMutation(): UseMutationResult<
  RegisterResponse,
  ApiError,
  RegisterRequest
> {
  return useMutation({
    mutationFn: register,
  });
}

export function useVerifyEmailMutation(): UseMutationResult<
  VerifyEmailResponse,
  ApiError,
  string
> {
  return useMutation({
    mutationFn: verifyEmail,
  });
}

export function useResendVerificationMutation(): UseMutationResult<
  ResendVerificationResponse,
  ApiError,
  string
> {
  return useMutation({
    mutationFn: resendVerification,
  });
}

export function useUpdateProfileMutation(): UseMutationResult<
  ProfileUpdateResponse,
  ApiError,
  ProfileUpdateRequest
> {
  return useMutation({
    mutationFn: updateProfile,
  });
}

export function useResetPasswordMutation(): UseMutationResult<
  PasswordResetCompleteResponse,
  ApiError,
  PasswordResetCompleteRequest
> {
  return useMutation({
    mutationFn: completePasswordReset,
  });
}

export function useMfaEnrollMutation(): UseMutationResult<
  MfaEnrollResponse,
  ApiError,
  void
> {
  return useMutation({
    mutationFn: enrollMfa,
  });
}

export function useMfaConfirmMutation(): UseMutationResult<
  MfaConfirmResponse,
  ApiError,
  MfaConfirmRequest
> {
  return useMutation({
    mutationFn: confirmMfa,
  });
}

export function useMfaRecoveryCodesRegenerateMutation(): UseMutationResult<
  MfaRecoveryCodesRegenerateResponse,
  ApiError,
  MfaRecoveryCodesRegenerateRequest
> {
  return useMutation({
    mutationFn: regenerateMfaRecoveryCodes,
  });
}

export function useMfaDisableMutation(): UseMutationResult<
  MfaDisableResponse,
  ApiError,
  MfaDisableRequest
> {
  return useMutation({
    mutationFn: disableMfa,
  });
}
