import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
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
    expect(screen.getByLabelText("Open signups")).toBeChecked();
    expect(saveButton).toBeDisabled();

    await user.click(screen.getByLabelText("Invite only"));

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

    await screen.findByLabelText("Open signups");
    await user.click(screen.getByLabelText("Invite only"));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(
      await screen.findByText(/Settings were changed by another administrator/i),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reload" }));

    await waitFor(() => {
      expect(screen.getByLabelText("Open signups")).toBeChecked();
    });
  });
});
