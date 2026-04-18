import { screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { OAuthProviderAdminPanel } from "@/components/features/auth/OAuthProviderAdminPanel";
import { renderWithProviders } from "@/test-utils/render";
import { setPlatformAdminUser } from "@/tests/features/admin/test-helpers";

describe("OAuthProviderAdminPanel", () => {
  beforeEach(() => {
    setPlatformAdminUser();
  });

  it("renders Google and GitHub provider forms", async () => {
    renderWithProviders(<OAuthProviderAdminPanel />);

    expect(await screen.findByText("Google")).toBeInTheDocument();
    expect(screen.getByText("GitHub")).toBeInTheDocument();
  });

  it("hydrates the GitHub card with the configured provider values", async () => {
    renderWithProviders(<OAuthProviderAdminPanel />);

    const githubHeading = await screen.findByText("GitHub");
    const githubCard = githubHeading.closest(".rounded-xl") as HTMLElement | null;
    if (!githubCard) {
      throw new Error("GitHub provider card container was not found");
    }

    await waitFor(() => {
      expect(within(githubCard).getByDisplayValue("GitHub")).toBeInTheDocument();
      expect(
        within(githubCard).getByDisplayValue("github-client-id"),
      ).toBeInTheDocument();
      expect(
        within(githubCard).getByDisplayValue("secret://github"),
      ).toBeInTheDocument();
    });
  });
});
