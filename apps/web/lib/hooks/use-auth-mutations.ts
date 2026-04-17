"use client";

import { useMutation, type UseMutationResult } from "@tanstack/react-query";
import {
  completePasswordReset,
  confirmMfa,
  enrollMfa,
  login,
  requestPasswordReset,
  verifyMfa,
  type LoginRequest,
  type LoginResponse,
  type MfaConfirmRequest,
  type MfaConfirmResponse,
  type MfaEnrollResponse,
  type MfaVerifyRequest,
  type MfaVerifyResponse,
  type PasswordResetCompleteRequest,
  type PasswordResetCompleteResponse,
  type PasswordResetRequestBody,
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
