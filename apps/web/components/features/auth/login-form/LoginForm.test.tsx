import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { LoginForm } from "@/components/features/auth/login-form/LoginForm";
import { toLoginSuccess } from "@/mocks/handlers";
import { renderWithProviders } from "@/test-utils/render";
import { server } from "@/vitest.setup";

describe("LoginForm", () => {
  it("shows validation errors and does not submit invalid forms", async () => {
    const user = userEvent.setup();
    const requestSpy = vi.fn();

    server.use(
      http.post("*/api/v1/auth/login", async ({ request }) => {
        requestSpy(await request.json());
        return HttpResponse.json(toLoginSuccess());
      }),
    );

    renderWithProviders(
      <LoginForm
        onLockout={vi.fn()}
        onMfaChallenge={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText("Enter a valid email address")).toBeInTheDocument();
    expect(await screen.findByText("Password is required")).toBeInTheDocument();
    expect(requestSpy).not.toHaveBeenCalled();
  });

  it("submits credentials and forwards successful login responses", async () => {
    const user = userEvent.setup();
    const onSuccess = vi.fn();

    renderWithProviders(
      <LoginForm
        onLockout={vi.fn()}
        onMfaChallenge={vi.fn()}
        onSuccess={onSuccess}
      />,
    );

    await user.type(screen.getByLabelText(/email/i), "alex@musematic.dev");
    await user.type(screen.getByLabelText(/^password$/i), "SecretPass1!");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledWith(
        expect.objectContaining({
          access_token: "mock-access-token",
        }),
      );
    });
  });

  it("shows a generic error for invalid credentials", async () => {
    const user = userEvent.setup();

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

    renderWithProviders(
      <LoginForm
        onLockout={vi.fn()}
        onMfaChallenge={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );

    await user.type(screen.getByLabelText(/email/i), "invalid@musematic.dev");
    await user.type(screen.getByLabelText(/^password$/i), "bad-password");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText("Invalid email or password")).toBeInTheDocument();
  });

  it("forwards lockout responses to the parent", async () => {
    const user = userEvent.setup();
    const onLockout = vi.fn();

    server.use(
      http.post("*/api/v1/auth/login", () =>
        HttpResponse.json(
          {
            error: {
              code: "ACCOUNT_LOCKED",
              message: "Account locked",
              lockout_seconds: 120,
            },
          },
          { status: 429 },
        ),
      ),
    );

    renderWithProviders(
      <LoginForm
        onLockout={onLockout}
        onMfaChallenge={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );

    await user.type(screen.getByLabelText(/email/i), "locked@musematic.dev");
    await user.type(screen.getByLabelText(/^password$/i), "SecretPass1!");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(onLockout).toHaveBeenCalledWith(120);
    });
  });

  it("transitions to MFA and supports pressing Enter in the password field", async () => {
    const user = userEvent.setup();
    const onMfaChallenge = vi.fn();

    server.use(
      http.post("*/api/v1/auth/login", () =>
        HttpResponse.json({
          mfa_required: true,
          session_token: "mfa-session-token",
        }),
      ),
    );

    renderWithProviders(
      <LoginForm
        onLockout={vi.fn()}
        onMfaChallenge={onMfaChallenge}
        onSuccess={vi.fn()}
      />,
    );

    await user.type(screen.getByLabelText(/email/i), "mfa@musematic.dev");
    await user.type(screen.getByLabelText(/^password$/i), "SecretPass1!{enter}");

    await waitFor(() => {
      expect(onMfaChallenge).toHaveBeenCalledWith("mfa-session-token");
    });
  });
});
