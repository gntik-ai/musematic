import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { MfaChallengeForm } from "@/components/features/auth/login-form/MfaChallengeForm";
import { renderWithProviders } from "@/test-utils/render";
import { server } from "@/vitest.setup";

describe("MfaChallengeForm", () => {
  it("auto-submits when a 6-digit code is entered", async () => {
    const user = userEvent.setup();
    const onSuccess = vi.fn();

    renderWithProviders(
      <MfaChallengeForm
        onBack={vi.fn()}
        onSuccess={onSuccess}
        sessionToken="mfa-session"
      />,
    );

    await user.type(screen.getByLabelText(/authenticator code/i), "123456");

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledWith(
        expect.objectContaining({
          access_token: "mock-access-token",
        }),
      );
    });
  });

  it("accepts pasted codes and auto-submits them", async () => {
    const onSuccess = vi.fn();

    renderWithProviders(
      <MfaChallengeForm
        onBack={vi.fn()}
        onSuccess={onSuccess}
        sessionToken="mfa-session"
      />,
    );

    const input = screen.getByLabelText(/authenticator code/i);
    fireEvent.change(input, { target: { value: "123456" } });

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledWith(
        expect.objectContaining({
          access_token: "mock-access-token",
        }),
      );
    });
  });

  it("clears the code and shows an error for invalid codes", async () => {
    const user = userEvent.setup();

    server.use(
      http.post("*/api/v1/auth/mfa/verify", () =>
        HttpResponse.json(
          {
            error: {
              code: "INVALID_CODE",
              message: "Invalid verification code",
            },
          },
          { status: 401 },
        ),
      ),
    );

    renderWithProviders(
      <MfaChallengeForm
        onBack={vi.fn()}
        onSuccess={vi.fn()}
        sessionToken="mfa-session"
      />,
    );

    const input = screen.getByLabelText(/authenticator code/i);
    await user.type(input, "654321");

    expect(await screen.findByText("Invalid verification code")).toBeInTheDocument();
    await waitFor(() => {
      expect(input).toHaveValue("");
    });
  });

  it("toggles between authenticator and recovery code inputs", async () => {
    const user = userEvent.setup();

    renderWithProviders(
      <MfaChallengeForm
        onBack={vi.fn()}
        onSuccess={vi.fn()}
        sessionToken="mfa-session"
      />,
    );

    await user.click(
      screen.getByRole("button", { name: /use a recovery code instead/i }),
    );

    expect(screen.getByLabelText(/recovery code/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("textbox", { name: /authenticator code/i }),
    ).not.toBeInTheDocument();
  });

  it("invokes onBack from the back link", async () => {
    const user = userEvent.setup();
    const onBack = vi.fn();

    renderWithProviders(
      <MfaChallengeForm
        onBack={onBack}
        onSuccess={vi.fn()}
        sessionToken="mfa-session"
      />,
    );

    await user.click(screen.getByRole("button", { name: /back to login/i }));

    expect(onBack).toHaveBeenCalledTimes(1);
  });
});
