import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Sidebar } from "@/components/layout/sidebar/Sidebar";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

vi.mock("next/navigation", () => ({
  usePathname: () => "/analytics",
}));

describe("Sidebar", () => {
  beforeEach(() => {
    useWorkspaceStore.setState({
      sidebarCollapsed: false,
      setSidebarCollapsed: vi.fn(),
    } as never);
  });

  it("filters nav items for viewer roles", () => {
    useAuthStore.setState({
      user: {
        id: "user-1",
        email: "viewer@musematic.dev",
        displayName: "Viewer",
        avatarUrl: null,
        roles: ["analytics_viewer"],
        workspaceId: "workspace-1",
      },
    } as never);

    render(<Sidebar />);

    expect(screen.getByText("Analytics")).toBeInTheDocument();
    expect(screen.queryByText("Policies")).not.toBeInTheDocument();
  });

  it("shows all nav items to superadmin", () => {
    useAuthStore.setState({
      user: {
        id: "user-1",
        email: "root@musematic.dev",
        displayName: "Root",
        avatarUrl: null,
        roles: ["superadmin"],
        workspaceId: "workspace-1",
      },
    } as never);

    render(<Sidebar />);

    expect(screen.getByText("Settings")).toBeInTheDocument();
    expect(screen.getByText("Policies")).toBeInTheDocument();
  });
});
