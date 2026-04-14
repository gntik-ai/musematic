import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import * as adminHooks from "@/lib/hooks/use-admin-settings";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SecurityTab } from "@/components/features/admin/tabs/SecurityTab";
import { securityPolicySchema } from "@/lib/schemas/admin";
import { renderWithProviders } from "@/test-utils/render";
import { setPlatformAdminUser } from "@/tests/features/admin/test-helpers";
import { server } from "@/vitest.setup";

const toast = vi.fn();

vi.mock("@/lib/hooks/use-toast", () => ({
  useToast: () => ({ toast }),
}));

describe("SecurityTab", () => {
  beforeEach(() => {
    toast.mockReset();
    setPlatformAdminUser();
  });

  it("pre-populates current values and shows the session rollout alert", async () => {
    renderWithProviders(<SecurityTab />);

    expect(await screen.findByDisplayValue("12")).toBeInTheDocument();
    expect(
      screen.getByText(/Changes apply only to new authentication events/i),
    ).toBeInTheDocument();
  });

  it("rejects invalid minimum password lengths in the schema and keeps save disabled before edits", async () => {
    renderWithProviders(<SecurityTab />);

    expect(await screen.findByDisplayValue("12")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();

    const result = securityPolicySchema.safeParse({
      lockout_duration_minutes: 15,
      lockout_max_attempts: 5,
      password_expiry_days: null,
      password_min_length: 7,
      password_require_digit: true,
      password_require_lowercase: true,
      password_require_special: true,
      password_require_uppercase: true,
      session_duration_minutes: 480,
    });

    expect(result.success).toBe(false);
    if (result.success) {
      return;
    }
    expect(result.error.flatten().fieldErrors.password_min_length).toContain(
      "Minimum 8 characters",
    );
  });

  it("saves valid changes to the security policy", async () => {
    const user = userEvent.setup();
    let capturedBody: unknown;

    server.use(
      http.patch("*/api/v1/admin/settings/security", async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json({
          password_min_length: 12,
          password_require_uppercase: true,
          password_require_lowercase: true,
          password_require_digit: true,
          password_require_special: true,
          password_expiry_days: null,
          session_duration_minutes: 60,
          lockout_max_attempts: 5,
          lockout_duration_minutes: 15,
          updated_at: "2026-04-12T12:00:00.000Z",
        });
      }),
    );

    renderWithProviders(<SecurityTab />);

    await screen.findByDisplayValue("12");
    await user.click(screen.getByRole("switch", { name: "Require digits" }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
    });
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(capturedBody).toEqual(
        expect.objectContaining({
          password_require_digit: false,
        }),
      );
    });
  });

  it("shows stale data state on 412 and reloads the latest policy", async () => {
    const user = userEvent.setup();

    server.use(
      http.patch("*/api/v1/admin/settings/security", () =>
        HttpResponse.json(
          {
            error: {
              code: "stale_data",
              message: "Security policy changed",
            },
          },
          { status: 412 },
        ),
      ),
    );

    renderWithProviders(<SecurityTab />);

    await screen.findByDisplayValue("12");
    await user.click(screen.getByRole("switch", { name: "Require digits" }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(
      await screen.findByText(/Settings were changed by another administrator/i),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reload" }));

    await waitFor(() => {
      expect(screen.getByRole("switch", { name: "Require digits" })).toBeChecked();
    });
  });

  it("shows inline validation errors for session and lockout bounds", async () => {
    const user = userEvent.setup();

    renderWithProviders(<SecurityTab />);

    await screen.findByDisplayValue("12");
    const sessionDuration = screen.getByLabelText("Session duration (minutes)");
    const lockoutAttempts = screen.getByLabelText("Maximum failed attempts");

    await user.clear(sessionDuration);
    await user.type(sessionDuration, "10");
    await user.clear(lockoutAttempts);
    await user.type(lockoutAttempts, "25");

    expect(await screen.findByText("Minimum 15 minutes")).toBeInTheDocument();
    expect(screen.getByText("Maximum 20 attempts")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("resets edits and reports unexpected save errors through toast", async () => {
    const user = userEvent.setup();

    server.use(
      http.patch("*/api/v1/admin/settings/security", () =>
        HttpResponse.json(
          {
            error: {
              code: "SECURITY_UPDATE_FAILED",
              message: "Security service unavailable",
            },
          },
          { status: 500 },
        ),
      ),
    );

    renderWithProviders(<SecurityTab />);

    await screen.findByDisplayValue("12");
    const expiryField = screen.getByLabelText("Password expiry (days)");
    await user.type(expiryField, "90");
    await user.click(screen.getByRole("button", { name: "Reset" }));

    await waitFor(() => {
      expect(screen.getByLabelText("Password expiry (days)")).toHaveValue(null);
    });

    await user.click(screen.getByRole("switch", { name: "Require digits" }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Security service unavailable",
          variant: "destructive",
        }),
      );
    });
  });

  it("returns early when security policy data has not loaded yet", async () => {
    const user = userEvent.setup();
    const policySpy = vi.spyOn(adminHooks, "useSecurityPolicy").mockReturnValue({
      data: undefined,
      refetch: vi.fn(),
    } as never);
    const mutation = vi.fn();
    const mutationSpy = vi.spyOn(adminHooks, "useSecurityPolicyMutation").mockReturnValue({
      isPending: false,
      mutateAsync: mutation,
    } as never);

    renderWithProviders(<SecurityTab />);

    await user.click(screen.getByRole("switch", { name: "Require digits" }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(mutation).not.toHaveBeenCalled();

    mutationSpy.mockRestore();
    policySpy.mockRestore();
  });

  it("falls back to a generic security settings error message for non-API failures", async () => {
    const user = userEvent.setup();
    const mutationSpy = vi.spyOn(adminHooks, "useSecurityPolicyMutation").mockReturnValue({
      isPending: false,
      mutateAsync: vi.fn().mockRejectedValue(new Error("timeout")),
    } as never);

    renderWithProviders(<SecurityTab />);

    await screen.findByDisplayValue("12");
    await user.click(screen.getByRole("switch", { name: "Require digits" }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Unable to update security settings",
          variant: "destructive",
        }),
      );
    });

    mutationSpy.mockRestore();
  });

  it("clears the saved state after the security form success timer elapses", async () => {
    const user = userEvent.setup();

    renderWithProviders(<SecurityTab />);

    await screen.findByDisplayValue("12");
    await user.click(screen.getByRole("switch", { name: "Require digits" }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("button", { name: /Saved ✓/i })).toBeInTheDocument();

    await new Promise((resolve) => setTimeout(resolve, 1600));

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /Saved ✓/i })).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    });
  });
});
