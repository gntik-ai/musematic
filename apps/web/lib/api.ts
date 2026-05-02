"use client";

import { refreshAccessToken } from "@/lib/auth";
import {
  MaintenanceBlockedError,
  emitMaintenanceBlocked,
  type MaintenanceBlockedDetails,
} from "@/lib/maintenance-blocked";
import { useAuthStore } from "@/store/auth-store";
import { ApiError, type ApiErrorPayload, type ApiRequestOptions } from "@/types/api";

interface ApiClient {
  get: <T>(path: string, options?: ApiRequestOptions) => Promise<T>;
  post: <T>(path: string, body?: unknown, options?: ApiRequestOptions) => Promise<T>;
  put: <T>(path: string, body?: unknown, options?: ApiRequestOptions) => Promise<T>;
  patch: <T>(path: string, body?: unknown, options?: ApiRequestOptions) => Promise<T>;
  delete: <T>(path: string, options?: ApiRequestOptions) => Promise<T>;
}

const BACKOFF_MS = [1000, 2000, 4000] as const;
const QUOTA_ERROR_CODES = new Set([
  "quota_exceeded",
  "overage_cap_exceeded",
  "model_tier_not_allowed",
]);

export interface QuotaErrorDetails {
  quota_name?: string | null;
  current?: number | string | null;
  limit?: number | string | null;
  reset_at?: string | null;
  plan_slug?: string | null;
  upgrade_url?: string | null;
  overage_available?: boolean | null;
}

export class QuotaError extends ApiError {
  public readonly quota: QuotaErrorDetails;

  constructor(payload: ApiErrorPayload, status: number) {
    super(payload.code, payload.message, status, undefined, payload);
    this.name = "QuotaError";
    this.quota = quotaDetails(payload.details);
  }
}

function isApiErrorPayload(value: unknown): value is { error: ApiErrorPayload } {
  if (typeof value !== "object" || value === null || !("error" in value)) {
    return false;
  }

  const error = (value as { error: unknown }).error;
  return typeof error === "object" && error !== null;
}

function getErrorPayload(value: unknown): ApiErrorPayload | null {
  if (isApiErrorPayload(value)) {
    return value.error;
  }
  if (
    typeof value === "object" &&
    value !== null &&
    "code" in value &&
    typeof (value as { code: unknown }).code === "string"
  ) {
    return value as ApiErrorPayload;
  }
  return null;
}

function maintenanceDetails(value: unknown): MaintenanceBlockedDetails {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as MaintenanceBlockedDetails)
    : {};
}

async function normalizeError(response: Response): Promise<never> {
  let payload: unknown;

  try {
    payload = await response.json();
  } catch {
    throw new ApiError("unknown_error", response.statusText || "Request failed", response.status);
  }

  const errorPayload = getErrorPayload(payload);
  if (errorPayload) {
    if (
      response.status === 503 &&
      errorPayload.code === "platform.maintenance.blocked"
    ) {
      const error = new MaintenanceBlockedError(
        errorPayload.message,
        response.status,
        maintenanceDetails(errorPayload.details),
      );
      emitMaintenanceBlocked(error);
      throw error;
    }

    if (response.status === 402 && QUOTA_ERROR_CODES.has(errorPayload.code)) {
      throw new QuotaError(errorPayload, response.status);
    }

    throw new ApiError(
      errorPayload.code,
      errorPayload.message,
      response.status,
      Array.isArray(errorPayload.details) ? errorPayload.details : undefined,
      errorPayload,
    );
  }

  throw new ApiError("unknown_error", response.statusText || "Request failed", response.status);
}

function quotaDetails(value: unknown): QuotaErrorDetails {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return {};
  }
  return value as QuotaErrorDetails;
}

async function wait(delayMs: number): Promise<void> {
  await new Promise((resolve) => {
    window.setTimeout(resolve, delayMs);
  });
}

function withOptionalBody(
  options: ApiRequestOptions | undefined,
  method: string,
  body?: unknown,
): ApiRequestOptions {
  if (body === undefined) {
    return { ...options, method };
  }

  return {
    ...options,
    method,
    body: isFormDataBody(body) ? body : JSON.stringify(body),
  };
}

function isFormDataBody(value: unknown): value is FormData {
  return typeof FormData !== "undefined" && value instanceof FormData;
}

export function createApiClient(baseUrl: string): ApiClient {
  const execute = async <T>(
    path: string,
    options: ApiRequestOptions = {},
    attempt = 0,
    refreshed = false,
  ): Promise<T> => {
    const { accessToken, clearAuth } = useAuthStore.getState();
    const headers = new Headers(options.headers);
    const hasBody = options.body !== undefined && options.body !== null;

    if (!headers.has("Content-Type") && hasBody && !isFormDataBody(options.body)) {
      headers.set("Content-Type", "application/json");
    }

    if (!options.skipAuth && accessToken) {
      headers.set("Authorization", `Bearer ${accessToken}`);
    }

    try {
      const response = await fetch(`${baseUrl}${path}`, {
        ...options,
        headers,
      });

      if (response.status === 401 && !options.skipAuth) {
        if (refreshed) {
          clearAuth();
          if (typeof window !== "undefined") {
            window.location.assign("/login");
          }
          throw new ApiError("unauthorized", "Unauthorized", response.status);
        }

        await refreshAccessToken();
        return execute<T>(path, options, attempt, true);
      }

      if (!response.ok) {
        return normalizeError(response);
      }

      if (response.status === 204) {
        return undefined as T;
      }

      return (await response.json()) as T;
    } catch (error) {
      if (error instanceof ApiError) {
        throw error;
      }

      const retryDelayMs = BACKOFF_MS.at(attempt);
      if (error instanceof TypeError && !options.skipRetry && retryDelayMs !== undefined) {
        await wait(retryDelayMs);
        return execute<T>(path, options, attempt + 1, refreshed);
      }

      throw error;
    }
  };

  return {
    get: <T>(path: string, options?: ApiRequestOptions) =>
      execute<T>(path, { ...options, method: "GET" }),
    post: <T>(path: string, body?: unknown, options?: ApiRequestOptions) =>
      execute<T>(path, withOptionalBody(options, "POST", body)),
    put: <T>(path: string, body?: unknown, options?: ApiRequestOptions) =>
      execute<T>(path, withOptionalBody(options, "PUT", body)),
    patch: <T>(path: string, body?: unknown, options?: ApiRequestOptions) =>
      execute<T>(path, withOptionalBody(options, "PATCH", body)),
    delete: <T>(path: string, options?: ApiRequestOptions) =>
      execute<T>(path, { ...options, method: "DELETE" }),
  };
}
