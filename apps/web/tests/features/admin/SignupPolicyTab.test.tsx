import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import * as adminHooks from "@/lib/hooks/use-admin-settings";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SignupPolicyTab } from "@/components/features/admin/tabs/SignupPolicyTab";
import { renderWithProviders } from "@/test-utils/render";
import { setPlatformAdminUser } from "@/tests/features/admin/test-helpers";
import { server } from "@/vitest.setup";

const toast = vi.fn();

vi.mock("@/lib/hooks/use-toast", () => ({
  useToast: () => ({ toast }),
}));

describe("SignupPolicyTab", () => {
  beforeEach(() => {
    toast.mockReset();
    setPlatformAdminUser();
  });

  it("pre-populates the form and saves changes with saved feedback", async () => {
    const user = userEvent.setup();

    renderWithProviders(<SignupPolicyTab />);

    const saveButton = await screen.findByRole("button", { name: "Save" });
    expect(screen.getByRole("radio", { name: /open signups/i })).toBeChecked();
    expect(saveButton).toBeDisabled();

    await user.click(screen.getByRole("radio", { name: /invite only/i }));

    expect(saveButton).toBeEnabled();
    await user.click(saveButton);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Saved ✓/i })).toBeInTheDocument();
    });
  });

  it("shows stale data alert on 412 and reloads the latest values", async () => {
    const user = userEvent.setup();

    server.use(
      http.patch("*/api/v1/admin/settings/signup", () =>
        HttpResponse.json(
          {
            error: {
              code: "stale_data",
              message: "Signup policy has changed",
            },
          },
          { status: 412 },
        ),
      ),
    );

    renderWithProviders(<SignupPolicyTab />);

    await screen.findByRole("radio", { name: /open signups/i });
    await user.click(screen.getByRole("radio", { name: /invite only/i }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(
      await screen.findByText(/Settings were changed by another administrator/i),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reload" }));

    await waitFor(() => {
      expect(screen.getByRole("radio", { name: /open signups/i })).toBeChecked();
    });
  });

  it("resets local edits and shows an error toast for unexpected failures", async () => {
    const user = userEvent.setup();

    server.use(
      http.patch("*/api/v1/admin/settings/signup", () =>
        HttpResponse.json(
          {
            error: {
              code: "SIGNUP_POLICY_FAILED",
              message: "Signup policy could not be saved",
            },
          },
          { status: 500 },
        ),
      ),
    );

    renderWithProviders(<SignupPolicyTab />);

    await screen.findByRole("radio", { name: /open signups/i });
    await user.click(screen.getByRole("switch", { name: "Toggle MFA enforcement" }));
    await user.click(screen.getByRole("button", { name: "Reset" }));

    expect(screen.getByRole("switch", { name: "Toggle MFA enforcement" })).not.toBeChecked();

    await user.click(screen.getByRole("radio", { name: /invite only/i }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Signup policy could not be saved",
          variant: "destructive",
        }),
      );
    });
  });

  it("returns early when signup policy data is not loaded yet", async () => {
    const user = userEvent.setup();
    const policySpy = vi.spyOn(adminHooks, "useSignupPolicy").mockReturnValue({
      data: undefined,
      refetch: vi.fn(),
    } as never);
    const mutation = vi.fn();
    const mutationSpy = vi.spyOn(adminHooks, "useSignupPolicyMutation").mockReturnValue({
      isPending: false,
      mutateAsync: mutation,
    } as never);

    renderWithProviders(<SignupPolicyTab />);

    await user.click(screen.getByRole("radio", { name: /invite only/i }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(mutation).not.toHaveBeenCalled();

    mutationSpy.mockRestore();
    policySpy.mockRestore();
  });

  it("falls back to a generic signup policy error message for non-API failures", async () => {
    const user = userEvent.setup();
    const mutationSpy = vi.spyOn(adminHooks, "useSignupPolicyMutation").mockReturnValue({
      isPending: false,
      mutateAsync: vi.fn().mockRejectedValue(new Error("timeout")),
    } as never);

    renderWithProviders(<SignupPolicyTab />);

    await screen.findByRole("radio", { name: /open signups/i });
    await user.click(screen.getByRole("radio", { name: /invite only/i }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Unable to update signup policy",
          variant: "destructive",
        }),
      );
    });

    mutationSpy.mockRestore();
  });
});
