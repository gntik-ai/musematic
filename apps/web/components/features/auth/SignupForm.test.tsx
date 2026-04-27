import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SignupForm } from "@/components/features/auth/SignupForm";
import { renderWithProviders } from "@/test-utils/render";
import { server } from "@/vitest.setup";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

async function fillValidSignupForm() {
  const user = userEvent.setup();

  await user.type(screen.getByLabelText(/^email$/i), "new.user@musematic.dev");
  await user.type(screen.getByLabelText(/display name/i), "New User");
  await user.type(screen.getByLabelText(/^password$/i), "StrongPass1!");
  await user.click(screen.getByLabelText(/AI disclosure/i));
  await user.click(screen.getByLabelText(/terms/i));

  return user;
}

describe("SignupForm", () => {
  beforeEach(() => {
    push.mockReset();
  });

  it("renders the signup fields and required consent controls", () => {
    renderWithProviders(<SignupForm />);

    expect(screen.getByLabelText(/^email$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/display name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/AI disclosure/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/terms/i)).toBeInTheDocument();
  });

  it("validates malformed email and weak password before submit", async () => {
    const user = userEvent.setup();
    const requestSpy = vi.fn();

    server.use(
      http.post("*/api/v1/accounts/register", async ({ request }) => {
        requestSpy(await request.json());
        return HttpResponse.json({ message: "accepted" }, { status: 202 });
      }),
    );

    renderWithProviders(<SignupForm />);

    await user.type(screen.getByLabelText(/^email$/i), "not-an-email");
    await user.type(screen.getByLabelText(/display name/i), "N");
    await user.type(screen.getByLabelText(/^password$/i), "weak");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText("Enter a valid email address")).toBeInTheDocument();
    expect(await screen.findAllByText("Minimum 12 characters")).toHaveLength(2);
    expect(requestSpy).not.toHaveBeenCalled();
  });

  it("submits registration and navigates to pending verification", async () => {
    let requestBody: unknown;

    server.use(
      http.post("*/api/v1/accounts/register", async ({ request }) => {
        requestBody = await request.json();
        return HttpResponse.json({ message: "accepted" }, { status: 202 });
      }),
    );

    renderWithProviders(<SignupForm />);

    const user = await fillValidSignupForm();
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => {
      expect(requestBody).toEqual({
        email: "new.user@musematic.dev",
        display_name: "New User",
        password: "StrongPass1!",
      });
    });
    expect(push).toHaveBeenCalledWith(
      "/verify-email/pending?email=new.user%40musematic.dev",
    );
  });

  it("renders the Retry-After countdown for rate limited registration", async () => {
    server.use(
      http.post("*/api/v1/accounts/register", () =>
        HttpResponse.json(
          {
            error: {
              code: "RATE_LIMIT_EXCEEDED",
              message: "Rate limit exceeded",
              retry_after: 90,
            },
          },
          { status: 429 },
        ),
      ),
    );

    renderWithProviders(<SignupForm />);

    const user = await fillValidSignupForm();
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText("You can try again in 90 seconds.")).toBeInTheDocument();
  });
});
