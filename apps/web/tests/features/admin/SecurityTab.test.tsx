import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { SecurityTab } from "@/components/features/admin/tabs/SecurityTab";
import { securityPolicySchema } from "@/lib/schemas/admin";
import { renderWithProviders } from "@/test-utils/render";
import { setPlatformAdminUser } from "@/tests/features/admin/test-helpers";
import { server } from "@/vitest.setup";

describe("SecurityTab", () => {
  beforeEach(() => {
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
});
