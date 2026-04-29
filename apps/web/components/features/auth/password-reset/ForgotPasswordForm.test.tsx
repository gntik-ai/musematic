import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ForgotPasswordForm } from "@/components/features/auth/password-reset/ForgotPasswordForm";
import { renderWithProviders } from "@/test-utils/render";
import { server } from "@/vitest.setup";

const assign = vi.fn();

describe("ForgotPasswordForm", () => {
  beforeEach(() => {
    assign.mockReset();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        ...window.location,
        assign,
      },
    });
  });

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

  it("offers linked OAuth recovery without changing the neutral reset confirmation", async () => {
    const user = userEvent.setup();

    server.use(
      http.get("*/api/v1/auth/oauth/links", ({ request }) => {
        const email = new URL(request.url).searchParams.get("email");
        if (email !== "alex@musematic.dev") {
          return HttpResponse.json({ items: [] });
        }

        return HttpResponse.json({
          items: [
            {
              display_name: "Google",
              external_avatar_url: null,
              external_email: "alex@musematic.dev",
              external_name: "Alex Mercer",
              last_login_at: "2026-04-18T07:30:00.000Z",
              linked_at: "2026-04-17T08:00:00.000Z",
              provider_type: "google",
            },
          ],
        });
      }),
      http.get("*/api/v1/auth/oauth/google/authorize", ({ request }) => {
        const url = new URL(request.url);
        expect(url.searchParams.get("intent")).toBe("recovery");
        expect(url.searchParams.get("email")).toBe("alex@musematic.dev");
        return HttpResponse.json({
          redirect_url: "https://oauth.example.com/google/recovery",
        });
      }),
    );

    renderWithProviders(<ForgotPasswordForm />);

    await user.type(screen.getByLabelText(/email/i), "alex@musematic.dev");
    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    expect(
      await screen.findByText(
        "If an account exists with this email, a reset link has been sent.",
      ),
    ).toBeInTheDocument();

    await user.click(
      await screen.findByRole("button", {
        name: "Sign in with Google to recover access",
      }),
    );

    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith(
        "https://oauth.example.com/google/recovery",
      );
    });
  });
});
