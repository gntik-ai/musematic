import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { EmailTab } from "@/components/features/admin/tabs/EmailTab";
import { renderWithProviders } from "@/test-utils/render";
import { setPlatformAdminUser } from "@/tests/features/admin/test-helpers";
import { server } from "@/vitest.setup";

describe("EmailTab", () => {
  beforeEach(() => {
    setPlatformAdminUser();
  });

  it("renders SMTP settings with a masked password and reveals the input on demand", async () => {
    const user = userEvent.setup();

    renderWithProviders(<EmailTab />);

    expect(await screen.findByDisplayValue("smtp.musematic.dev")).toBeInTheDocument();
    const passwordField = screen.getByLabelText("SMTP password");
    expect(passwordField).toBeDisabled();
    expect(passwordField).toHaveValue("••••••••");

    await user.click(screen.getByRole("button", { name: "Update SMTP password" }));

    expect(passwordField).toBeEnabled();
    expect(passwordField).toHaveValue("");

    await user.selectOptions(screen.getByLabelText("Delivery mode"), "ses");

    expect(screen.getByLabelText("SES region")).toBeInTheDocument();
  });

  it("omits new_password when saving without editing credentials", async () => {
    const user = userEvent.setup();
    let capturedBody: unknown;

    server.use(
      http.patch("*/api/v1/admin/settings/email", async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json({
          mode: "smtp",
          smtp: {
            host: "smtp.musematic.dev",
            port: 587,
            username: "mailer",
            password_set: true,
            encryption: "starttls",
          },
          from_address: "noreply@musematic.dev",
          from_name: "Musematic Ops",
          verification_status: "verified",
          last_delivery_at: "2026-04-12T07:10:00.000Z",
          updated_at: "2026-04-12T12:00:00.000Z",
        });
      }),
    );

    renderWithProviders(<EmailTab />);

    await screen.findByDisplayValue("smtp.musematic.dev");
    await user.clear(screen.getByLabelText("From name"));
    await user.type(screen.getByLabelText("From name"), "Musematic Ops");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(capturedBody).toEqual(
        expect.not.objectContaining({
          new_password: expect.anything(),
        }),
      );
    });
  });

  it("sends a test email and shows the result", async () => {
    const user = userEvent.setup();

    renderWithProviders(<EmailTab />);

    await screen.findByDisplayValue("smtp.musematic.dev");
    await user.type(screen.getByLabelText("Recipient"), "test@example.com");
    await user.click(screen.getByRole("button", { name: "Send Test Email" }));

    expect(await screen.findByText("Test email sent successfully")).toBeInTheDocument();
  });
});
