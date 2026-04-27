import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConnectedAccountsSection } from "@/components/features/auth/ConnectedAccountsSection";
import { oauthFixtures } from "@/mocks/handlers/oauth";
import { useAuthStore } from "@/store/auth-store";
import type { OAuthLinkResponse } from "@/lib/types/oauth";
import { renderWithProviders } from "@/test-utils/render";

const assign = vi.fn();

function setAuthenticatedUser(hasLocalPassword = true) {
  useAuthStore.setState({
    accessToken: "access-token",
    isAuthenticated: true,
    refreshToken: "refresh-token",
    user: {
      id: "user-1",
      email: "alex@musematic.dev",
      displayName: "Alex Mercer",
      avatarUrl: null,
      mfaEnrolled: true,
      hasLocalPassword,
      roles: ["workspace_admin"],
      workspaceId: "workspace-1",
    },
  } as never);
}

function buildLink(
  providerType: "google" | "github",
  email: string,
): OAuthLinkResponse {
  return {
    display_name: providerType === "google" ? "Google" : "GitHub",
    external_avatar_url: null,
    external_email: email,
    external_name: providerType === "google" ? "Alex Mercer" : "Octo Cat",
    last_login_at: "2026-04-18T07:30:00.000Z",
    linked_at: "2026-04-17T08:00:00.000Z",
    provider_type: providerType,
  };
}

describe("ConnectedAccountsSection", () => {
  beforeEach(() => {
    assign.mockReset();
    setAuthenticatedUser();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        ...window.location,
        assign,
      },
    });
  });

  it("starts the link flow for available providers", async () => {
    const user = userEvent.setup();

    oauthFixtures.links = [buildLink("google", "alex@musematic.dev")];

    renderWithProviders(<ConnectedAccountsSection />);

    const linkGitHub = await screen.findByRole("button", {
      name: "Link GitHub",
    });
    await user.click(linkGitHub);

    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith("https://oauth.example.com/github/link");
    });
  });

  it("surfaces the 409 guard when unlinking the last remaining method", async () => {
    const user = userEvent.setup();

    oauthFixtures.links = [buildLink("google", "alex@musematic.dev")];

    renderWithProviders(<ConnectedAccountsSection />);

    await user.click(await screen.findByRole("button", { name: "Unlink" }));
    await user.type(screen.getByPlaceholderText("google"), "google");
    await user.click(screen.getByRole("button", { name: "Unlink provider" }));

    expect(
      await screen.findByText(
        "Cannot unlink: this is your only authentication method.",
      ),
    ).toBeInTheDocument();
  });

  it("removes a provider after a successful unlink", async () => {
    const user = userEvent.setup();

    oauthFixtures.links = [
      buildLink("google", "alex@musematic.dev"),
      buildLink("github", "octocat@musematic.dev"),
    ];

    renderWithProviders(<ConnectedAccountsSection />);

    const unlinkButtons = await screen.findAllByRole("button", { name: "Unlink" });
    const firstButton = unlinkButtons[0];
    if (!firstButton) {
      throw new Error("Expected at least one unlink button");
    }

    await user.click(firstButton);
    await user.type(screen.getByPlaceholderText("google"), "google");
    await user.click(screen.getByRole("button", { name: "Unlink provider" }));

    await waitFor(() => {
      expect(screen.queryByText("alex@musematic.dev")).not.toBeInTheDocument();
    });
  });

  it("disables unlinking when OAuth is the only auth method", async () => {
    setAuthenticatedUser(false);
    oauthFixtures.links = [buildLink("google", "alex@musematic.dev")];

    renderWithProviders(<ConnectedAccountsSection />);

    const unlinkButton = await screen.findByRole("button", { name: "Unlink" });

    expect(unlinkButton).toBeDisabled();
    expect(unlinkButton).toHaveAttribute(
      "title",
      "You must keep at least one authentication method. Set a local password or link another provider first.",
    );
  });
});
