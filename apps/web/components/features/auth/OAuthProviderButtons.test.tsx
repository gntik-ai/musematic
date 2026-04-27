import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { OAuthProviderButtons } from "@/components/features/auth/OAuthProviderButtons";
import { oauthFixtures } from "@/mocks/handlers/oauth";
import { renderWithProviders } from "@/test-utils/render";

const assign = vi.fn();

describe("OAuthProviderButtons", () => {
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

  it("loads enabled providers and redirects to the selected authorization URL", async () => {
    const user = userEvent.setup();

    renderWithProviders(<OAuthProviderButtons />);

    const googleButton = await screen.findByRole("button", {
      name: "Continue with Google",
    });

    expect(
      screen.getByRole("button", { name: "Continue with GitHub" }),
    ).toBeInTheDocument();

    await user.click(googleButton);

    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith(
        "https://oauth.example.com/google/authorize",
      );
    });
  });


  it("shows only the providers currently enabled by the public endpoint", async () => {
    oauthFixtures.providers.google.enabled = false;

    renderWithProviders(<OAuthProviderButtons />);

    expect(
      screen.queryByRole("button", { name: "Continue with Google" }),
    ).not.toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "Continue with GitHub" }),
    ).toBeInTheDocument();
  });

  it("renders signup labels for the signup variant", async () => {
    renderWithProviders(<OAuthProviderButtons variant="signup" />);

    expect(
      await screen.findByRole("button", { name: "Sign up with Google" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Sign up with GitHub" }),
    ).toBeInTheDocument();
  });

  it("keeps continue labels as the default login variant", async () => {
    renderWithProviders(<OAuthProviderButtons />);

    expect(
      await screen.findByRole("button", { name: "Continue with Google" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Continue with GitHub" }),
    ).toBeInTheDocument();
  });
});
