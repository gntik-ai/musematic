import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { ForgotPasswordForm } from "@/components/features/auth/password-reset/ForgotPasswordForm";
import { renderWithProviders } from "@/test-utils/render";
import { server } from "@/vitest.setup";

describe("ForgotPasswordForm", () => {
  it("validates email input before submitting", async () => {
    const user = userEvent.setup();

    renderWithProviders(<ForgotPasswordForm />);

    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    expect(await screen.findByText("Enter a valid email address")).toBeInTheDocument();
  });

  it.each([
    { status: 202, body: {} },
    {
      status: 404,
      body: {
        error: {
          code: "NOT_FOUND",
          message: "No account",
        },
      },
    },
    {
      status: 500,
      body: {
        error: {
          code: "SERVER_ERROR",
          message: "Unexpected",
        },
      },
    },
  ])(
    "shows the same confirmation message for response status $status",
    async ({ body, status }) => {
      const user = userEvent.setup();

      server.use(
        http.post("*/api/v1/password-reset/request", () =>
          HttpResponse.json(body, { status }),
        ),
      );

      renderWithProviders(<ForgotPasswordForm />);

      await user.type(screen.getByLabelText(/email/i), "alex@musematic.dev");
      await user.click(screen.getByRole("button", { name: /send reset link/i }));

      await waitFor(() => {
        expect(
          screen.getByText(
            "If an account exists with this email, a reset link has been sent.",
          ),
        ).toBeInTheDocument();
      });
    },
  );
});
