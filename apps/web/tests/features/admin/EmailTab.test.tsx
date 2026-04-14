import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import * as adminHooks from "@/lib/hooks/use-admin-settings";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { EmailTab } from "@/components/features/admin/tabs/EmailTab";
import { renderWithProviders } from "@/test-utils/render";
import { setPlatformAdminUser } from "@/tests/features/admin/test-helpers";
import { server } from "@/vitest.setup";

const toast = vi.fn();

vi.mock("@/lib/hooks/use-toast", () => ({
  useToast: () => ({ toast }),
}));

describe("EmailTab", () => {
  beforeEach(() => {
    toast.mockReset();
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

  it("shows an error alert when the test email request fails", async () => {
    const user = userEvent.setup();

    server.use(
      http.post("*/api/v1/admin/settings/email/test", () =>
        HttpResponse.json(
          {
            error: {
              code: "EMAIL_TEST_FAILED",
              message: "SMTP handshake failed",
            },
          },
          { status: 502 },
        ),
      ),
    );

    renderWithProviders(<EmailTab />);

    await screen.findByDisplayValue("smtp.musematic.dev");
    await user.type(screen.getByLabelText("Recipient"), "test@example.com");
    await user.click(screen.getByRole("button", { name: "Send Test Email" }));

    expect(await screen.findByText("Test email failed")).toBeInTheDocument();
    expect(screen.getByText("SMTP handshake failed")).toBeInTheDocument();
  });

  it("saves SES credentials and includes a new secret only when editing is enabled", async () => {
    const user = userEvent.setup();
    let capturedBody: unknown;

    server.use(
      http.get("*/api/v1/admin/settings/email", () =>
        HttpResponse.json({
          mode: "ses",
          ses: {
            region: "eu-west-1",
            access_key_id: "AKIA123",
            secret_access_key_set: true,
          },
          from_address: "alerts@musematic.dev",
          from_name: "Musematic SES",
          verification_status: "pending",
          updated_at: "2026-04-12T12:00:00.000Z",
        }),
      ),
      http.patch("*/api/v1/admin/settings/email", async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json({
          mode: "ses",
          ses: {
            region: "eu-west-1",
            access_key_id: "AKIA123",
            secret_access_key_set: true,
          },
          from_address: "alerts@musematic.dev",
          from_name: "Musematic SES",
          verification_status: "pending",
          updated_at: "2026-04-13T09:00:00.000Z",
        });
      }),
    );

    renderWithProviders(<EmailTab />);

    expect(await screen.findByDisplayValue("AKIA123")).toBeInTheDocument();
    expect(screen.getByText("Verification is pending.")).toBeInTheDocument();

    const secretField = screen.getByLabelText("SES secret access key");
    expect(secretField).toBeDisabled();
    expect(secretField).toHaveValue("••••••••");

    await user.click(screen.getByRole("button", { name: "Update SES secret access key" }));
    await user.type(secretField, "ses-secret-value");
    await user.clear(screen.getByLabelText("From name"));
    await user.type(screen.getByLabelText("From name"), "Musematic SES");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(capturedBody).toEqual(
        expect.objectContaining({
          mode: "ses",
          new_secret_access_key: "ses-secret-value",
        }),
      );
    });
  });

  it("shows stale data reload for the settings form and resets edited password state", async () => {
    const user = userEvent.setup();

    server.use(
      http.patch("*/api/v1/admin/settings/email", () =>
        HttpResponse.json(
          {
            error: {
              code: "stale_data",
              message: "Email settings changed",
            },
          },
          { status: 412 },
        ),
      ),
    );

    renderWithProviders(<EmailTab />);

    await screen.findByDisplayValue("smtp.musematic.dev");
    await user.click(screen.getByRole("button", { name: "Update SMTP password" }));
    await user.type(screen.getByLabelText("SMTP password"), "new-secret");
    await user.clear(screen.getByLabelText("From name"));
    await user.type(screen.getByLabelText("From name"), "Changed sender");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(
      await screen.findByText(/Settings were changed by another administrator/i),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reload" }));

    await waitFor(() => {
      expect(screen.getByLabelText("From name")).toHaveValue("Musematic");
      expect(screen.getByLabelText("SMTP password")).toBeDisabled();
      expect(screen.getByLabelText("SMTP password")).toHaveValue("••••••••");
    });
  });

  it("resets SMTP edits and reports API failures through toast", async () => {
    const user = userEvent.setup();

    server.use(
      http.patch("*/api/v1/admin/settings/email", () =>
        HttpResponse.json(
          {
            error: {
              code: "EMAIL_UPDATE_FAILED",
              message: "Provider rejected the configuration",
            },
          },
          { status: 500 },
        ),
      ),
    );

    renderWithProviders(<EmailTab />);

    await screen.findByDisplayValue("smtp.musematic.dev");
    await user.click(screen.getByRole("button", { name: "Update SMTP password" }));
    await user.type(screen.getByLabelText("SMTP password"), "edited-secret");
    await user.clear(screen.getByLabelText("From name"));
    await user.type(screen.getByLabelText("From name"), "Edited sender");
    await user.click(screen.getByRole("button", { name: "Reset" }));

    await waitFor(() => {
      expect(screen.getByLabelText("From name")).toHaveValue("Musematic");
      expect(screen.getByLabelText("SMTP password")).toBeDisabled();
      expect(screen.getByLabelText("SMTP password")).toHaveValue("••••••••");
    });

    await user.clear(screen.getByLabelText("From name"));
    await user.type(screen.getByLabelText("From name"), "Broken sender");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Provider rejected the configuration",
          variant: "destructive",
        }),
      );
    });
  });

  it("updates the SMTP port and clears the saved state after the success timer elapses", async () => {
    const user = userEvent.setup();

    renderWithProviders(<EmailTab />);

    await screen.findByDisplayValue("smtp.musematic.dev");
    const portInput = screen.getByLabelText("SMTP port");
    await user.clear(portInput);
    await user.type(portInput, "2525");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("button", { name: /Saved ✓/i })).toBeInTheDocument();

    await new Promise((resolve) => setTimeout(resolve, 1600));

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /Saved ✓/i })).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    });
  });

  it("falls back to a generic email settings error for non-API failures", async () => {
    const user = userEvent.setup();
    const mutationSpy = vi.spyOn(adminHooks, "useEmailConfigMutation").mockReturnValue({
      isPending: false,
      mutateAsync: vi.fn().mockRejectedValue(new Error("socket hang up")),
    } as never);

    renderWithProviders(<EmailTab />);

    await screen.findByDisplayValue("smtp.musematic.dev");
    await user.clear(screen.getByLabelText("From name"));
    await user.type(screen.getByLabelText("From name"), "Broken sender");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Unable to update email settings",
          variant: "destructive",
        }),
      );
    });

    mutationSpy.mockRestore();
  });

  it("falls back to a generic test email error for non-API failures", async () => {
    const user = userEvent.setup();
    const mutationSpy = vi.spyOn(adminHooks, "useSendTestEmailMutation").mockReturnValue({
      isPending: false,
      mutateAsync: vi.fn().mockRejectedValue(new Error("smtp timeout")),
    } as never);

    renderWithProviders(<EmailTab />);

    await screen.findByDisplayValue("smtp.musematic.dev");
    await user.type(screen.getByLabelText("Recipient"), "test@example.com");
    await user.click(screen.getByRole("button", { name: "Send Test Email" }));

    expect(await screen.findByText("Unable to send test email")).toBeInTheDocument();

    mutationSpy.mockRestore();
  });

  it("returns early when the settings query is not loaded yet", async () => {
    const user = userEvent.setup();
    const querySpy = vi.spyOn(adminHooks, "useEmailConfig").mockReturnValue({
      data: undefined,
      refetch: vi.fn(),
    } as never);
    const mutation = vi.fn();
    const mutationSpy = vi.spyOn(adminHooks, "useEmailConfigMutation").mockReturnValue({
      isPending: false,
      mutateAsync: mutation,
    } as never);

    renderWithProviders(<EmailTab />);

    await user.clear(screen.getByLabelText("From name"));
    await user.type(screen.getByLabelText("From name"), "Early submit");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(mutation).not.toHaveBeenCalled();

    mutationSpy.mockRestore();
    querySpy.mockRestore();
  });
});
