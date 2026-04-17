"use client";

import { refreshAccessToken } from "@/lib/auth";
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

function isApiErrorPayload(value: unknown): value is { error: ApiErrorPayload } {
  if (typeof value !== "object" || value === null || !("error" in value)) {
    return false;
  }

  const error = (value as { error: unknown }).error;
  return typeof error === "object" && error !== null;
}

async function normalizeError(response: Response): Promise<never> {
  let payload: unknown;

  try {
    payload = await response.json();
  } catch {
    throw new ApiError("unknown_error", response.statusText || "Request failed", response.status);
  }

  if (isApiErrorPayload(payload)) {
    throw new ApiError(
      payload.error.code,
      payload.error.message,
      response.status,
      payload.error.details,
      payload.error,
    );
  }

  throw new ApiError("unknown_error", response.statusText || "Request failed", response.status);
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
    body: JSON.stringify(body),
  };
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

    if (!headers.has("Content-Type") && options.body) {
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
