import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { SecurityTab } from "@/components/features/admin/tabs/SecurityTab";
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

  it("shows validation errors and disables save while invalid", async () => {
    const user = userEvent.setup();

    renderWithProviders(<SecurityTab />);

    const minLengthInput = await screen.findByLabelText("Minimum password length");
    await user.clear(minLengthInput);
    await user.type(minLengthInput, "7");

    expect(await screen.findByText("Minimum 8 characters")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
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

    const sessionInput = await screen.findByLabelText("Session duration (minutes)");
    await user.clear(sessionInput);
    await user.type(sessionInput, "60");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(capturedBody).toEqual(
        expect.objectContaining({
          session_duration_minutes: 60,
        }),
      );
    });
  });
});
