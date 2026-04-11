import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ResetPasswordForm } from "@/components/features/auth/password-reset/ResetPasswordForm";
import { renderWithProviders } from "@/test-utils/render";
import { server } from "@/vitest.setup";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

describe("ResetPasswordForm", () => {
  beforeEach(() => {
    push.mockReset();
  });

  it("updates each password rule indicator independently", async () => {
    const user = userEvent.setup();

    renderWithProviders(<ResetPasswordForm token="valid-token" />);

    const lengthRule = screen.getByText("Minimum 12 characters").closest("li");
    const uppercaseRule = screen.getByText("Uppercase letter").closest("li");

    expect(lengthRule).toHaveAttribute("data-state", "pending");
    expect(uppercaseRule).toHaveAttribute("data-state", "pending");

    await user.type(screen.getByLabelText(/new password/i), "StrongPass1!");

    expect(lengthRule).toHaveAttribute("data-state", "passed");
    expect(uppercaseRule).toHaveAttribute("data-state", "passed");
    expect(screen.getByText("Special character").closest("li")).toHaveAttribute(
      "data-state",
      "passed",
    );
  });

  it("keeps submit disabled while rules fail or passwords do not match", async () => {
    const user = userEvent.setup();

    renderWithProviders(<ResetPasswordForm token="valid-token" />);

    const submitButton = screen.getByRole("button", { name: /update password/i });
    expect(submitButton).toBeDisabled();

    await user.type(screen.getByLabelText(/new password/i), "StrongPass1!");
    await user.type(screen.getByLabelText(/confirm password/i), "Mismatch123!");

    expect(await screen.findByText("Passwords do not match")).toBeInTheDocument();
    expect(submitButton).toBeDisabled();
  });

  it("navigates back to login after a successful reset", async () => {
    const user = userEvent.setup();

    renderWithProviders(<ResetPasswordForm token="valid-token" />);

    await user.type(screen.getByLabelText(/new password/i), "StrongPass1!");
    await user.type(screen.getByLabelText(/confirm password/i), "StrongPass1!");
    await user.click(screen.getByRole("button", { name: /update password/i }));

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith("/login?message=password_updated");
    });
  });

  it("shows an error state and a new-link action for expired tokens", async () => {
    const user = userEvent.setup();

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

    renderWithProviders(<ResetPasswordForm token="expired-token" />);

    await user.type(screen.getByLabelText(/new password/i), "StrongPass1!");
    await user.type(screen.getByLabelText(/confirm password/i), "StrongPass1!");
    await user.click(screen.getByRole("button", { name: /update password/i }));

    expect(await screen.findByText("This reset link can't be used")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /request a new link/i })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
  });
});
