import { describe, expect, it, vi } from "vitest";
import { queryClient } from "@/lib/query-client";
import { useWorkspaceStore } from "@/store/workspace-store";

describe("workspace-store", () => {
  it("invalidates queries when the current workspace changes", () => {
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue(undefined);

    useWorkspaceStore.getState().setCurrentWorkspace({
      id: "workspace-1",
      name: "Signal Lab",
      slug: "signal-lab",
      description: null,
      memberCount: 18,
      createdAt: new Date().toISOString(),
    });

    expect(invalidateSpy).toHaveBeenCalled();
  });

  it("persists collapsed sidebar state", () => {
    useWorkspaceStore.getState().setSidebarCollapsed(true);
    expect(localStorage.getItem("workspace-storage")).toContain("sidebarCollapsed");
  });
});
