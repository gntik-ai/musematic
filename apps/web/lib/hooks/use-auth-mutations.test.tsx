import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import type { PropsWithChildren, ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import {
  useForgotPasswordMutation,
  useLoginMutation,
  useMfaConfirmMutation,
  useMfaEnrollMutation,
  useMfaVerifyMutation,
  useResetPasswordMutation,
} from "@/lib/hooks/use-auth-mutations";
import { toLoginSuccess } from "@/mocks/handlers";
import { useAuthStore } from "@/store/auth-store";
import type { ApiError } from "@/types/api";
import { server } from "@/vitest.setup";

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
      queries: { retry: false },
    },
  });

  return function Wrapper({ children }: PropsWithChildren): ReactNode {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

describe("use-auth-mutations", () => {
  beforeEach(() => {
    useAuthStore.setState({
      accessToken: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,
      isLoading: false,
    } as never);
  });

  it("submits login credentials and returns the success payload", async () => {
    let requestBody: unknown;

    server.use(
      http.post("*/api/v1/auth/login", async ({ request }) => {
        requestBody = await request.json();
        return HttpResponse.json(toLoginSuccess());
      }),
    );

    const { result } = renderHook(() => useLoginMutation(), {
      wrapper: createWrapper(),
    });

    let response: unknown;
    await act(async () => {
      response = await result.current.mutateAsync({
        email: "alex@musematic.dev",
        password: "SecretPass1!",
      });
    });

    expect(requestBody).toEqual({
      email: "alex@musematic.dev",
      password: "SecretPass1!",
    });
    expect(response).toMatchObject({
      access_token: "mock-access-token",
      refresh_token: "mock-refresh-token",
    });
  });

  it("surfaces login errors as ApiError", async () => {
    server.use(
      http.post("*/api/v1/auth/login", () =>
        HttpResponse.json(
          {
            error: {
              code: "INVALID_CREDENTIALS",
              message: "Invalid email or password",
            },
          },
          { status: 401 },
        ),
      ),
    );

    const { result } = renderHook(() => useLoginMutation(), {
      wrapper: createWrapper(),
    });

    await expect(
      result.current.mutateAsync({
        email: "invalid@musematic.dev",
        password: "nope",
      }),
    ).rejects.toEqual(
      expect.objectContaining<Partial<ApiError>>({
        code: "INVALID_CREDENTIALS",
        status: 401,
      }),
    );
  });

  it("verifies MFA codes and forwards recovery code usage", async () => {
    let requestBody: unknown;

    server.use(
      http.post("*/api/v1/auth/mfa/verify", async ({ request }) => {
        requestBody = await request.json();
        return HttpResponse.json({
          ...toLoginSuccess(),
          recovery_code_consumed: true,
        });
      }),
    );

    const { result } = renderHook(() => useMfaVerifyMutation(), {
      wrapper: createWrapper(),
    });

    let response: unknown;
    await act(async () => {
      response = await result.current.mutateAsync({
        session_token: "mfa-token",
        code: "recovery-code",
        use_recovery_code: true,
      });
    });

    expect(requestBody).toEqual({
      session_token: "mfa-token",
      code: "recovery-code",
      use_recovery_code: true,
    });
    expect(response).toMatchObject({ recovery_code_consumed: true });
  });

  it("requests password resets without requiring auth", async () => {
    let requestBody: unknown;

    server.use(
      http.post("*/api/v1/password-reset/request", async ({ request }) => {
        requestBody = await request.json();
        return HttpResponse.json({}, { status: 202 });
      }),
    );

    const { result } = renderHook(() => useForgotPasswordMutation(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync({ email: "alex@musematic.dev" });
    });

    expect(requestBody).toEqual({ email: "alex@musematic.dev" });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
  });

  it("completes password resets with the expected request body", async () => {
    let requestBody: unknown;

    server.use(
      http.post("*/api/v1/password-reset/complete", async ({ request }) => {
        requestBody = await request.json();
        return HttpResponse.json({ success: true });
      }),
    );

    const { result } = renderHook(() => useResetPasswordMutation(), {
      wrapper: createWrapper(),
    });

    let response: unknown;
    await act(async () => {
      response = await result.current.mutateAsync({
        token: "reset-token",
        new_password: "StrongPassword1!",
      });
    });

    expect(requestBody).toEqual({
      token: "reset-token",
      new_password: "StrongPassword1!",
    });
    expect(response).toEqual({ success: true });
  });

  it("surfaces token reset errors", async () => {
    server.use(
      http.post("*/api/v1/password-reset/complete", () =>
        HttpResponse.json(
          {
            error: {
              code: "TOKEN_EXPIRED",
              message: "Token expired",
            },
          },
          { status: 400 },
        ),
      ),
    );

    const { result } = renderHook(() => useResetPasswordMutation(), {
      wrapper: createWrapper(),
    });

    await expect(
      result.current.mutateAsync({
        token: "expired-token",
        new_password: "StrongPassword1!",
      }),
    ).rejects.toEqual(
      expect.objectContaining<Partial<ApiError>>({
        code: "TOKEN_EXPIRED",
        status: 400,
      }),
    );
  });

  it("loads MFA enrollment data using the authenticated session", async () => {
    useAuthStore.setState({
      accessToken: "access-token",
      isAuthenticated: true,
    } as never);

    const { result } = renderHook(() => useMfaEnrollMutation(), {
      wrapper: createWrapper(),
    });

    let response: unknown;
    await act(async () => {
      response = await result.current.mutateAsync();
    });

    expect(response).toMatchObject({
      provisioning_uri: expect.stringContaining("otpauth://"),
      secret_key: expect.any(String),
    });
  });

  it("confirms MFA enrollment and returns recovery codes", async () => {
    let requestBody: unknown;

    server.use(
      http.post("*/api/v1/auth/mfa/confirm", async ({ request }) => {
        requestBody = await request.json();
        return HttpResponse.json({
          recovery_codes: ["alpha", "bravo"],
        });
      }),
    );

    const { result } = renderHook(() => useMfaConfirmMutation(), {
      wrapper: createWrapper(),
    });

    let response: unknown;
    await act(async () => {
      response = await result.current.mutateAsync({ code: "123456" });
    });

    expect(requestBody).toEqual({ totp_code: "123456" });
    expect(response).toEqual({ recovery_codes: ["alpha", "bravo"] });
  });
});
