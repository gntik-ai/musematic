import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { OAuthProviderButtons } from "@/components/features/auth/OAuthProviderButtons";
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
});
