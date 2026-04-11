import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { QuickActions } from "@/components/features/home/QuickActions";
import { renderWithProviders } from "@/test-utils/render";
import { useAuthStore } from "@/store/auth-store";

describe("QuickActions", () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: {
        id: "user-1",
        email: "owner@musematic.dev",
        displayName: "Owner",
        avatarUrl: null,
        roles: ["workspace_admin"],
        workspaceId: "workspace-1",
        mfaEnrolled: true,
      },
    });
  });

  it("renders all quick actions enabled for workspace owners/admins", () => {
    renderWithProviders(<QuickActions />);

    expect(
      screen.getByRole("link", { name: "New Conversation" }),
    ).toHaveAttribute("href", "/conversations/new");
    expect(
      screen.getByRole("link", { name: "Upload Agent" }),
    ).toHaveAttribute("href", "/agents/create");
    expect(
      screen.getByRole("link", { name: "Create Workflow" }),
    ).toHaveAttribute("href", "/workflows");
    expect(
      screen.getByRole("link", { name: "Browse Marketplace" }),
    ).toHaveAttribute("href", "/marketplace");
  });

  it("disables write actions for viewer-only users and exposes the tooltip text", () => {
    useAuthStore.setState({
      user: {
        id: "user-2",
        email: "viewer@musematic.dev",
        displayName: "Viewer",
        avatarUrl: null,
        roles: ["workspace_viewer"],
        workspaceId: "workspace-1",
        mfaEnrolled: true,
      },
    });

    renderWithProviders(<QuickActions />);

    expect(
      screen.getByRole("button", { name: "Upload Agent" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Create Workflow" }),
    ).toBeDisabled();
    expect(screen.getAllByText("Requires write access").length).toBeGreaterThan(0);
  });
});
