import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { createHookWrapper } from "@/lib/hooks/__tests__/test-utils";
import { useWorkflowList } from "@/lib/hooks/use-workflow-list";
import { useWorkspaceStore } from "@/store/workspace-store";

describe("useWorkflowList", () => {
  beforeEach(() => {
    useWorkspaceStore.setState({
      currentWorkspace: {
        id: "workspace-1",
        name: "Operations",
        slug: "operations",
        description: "Ops workspace",
        memberCount: 4,
        createdAt: "2026-04-13T08:00:00.000Z",
      },
      workspaceList: [],
      sidebarCollapsed: false,
      isLoading: false,
    });
  });

  it("loads paginated workflows for the current workspace", async () => {
    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(() => useWorkflowList({ limit: 1 }), {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.pages[0]?.items).toEqual([
      expect.objectContaining({
        id: "workflow-1",
        name: "KYC Onboarding",
      }),
    ]);
    expect(result.current.hasNextPage).toBe(true);

    await act(async () => {
      await result.current.fetchNextPage();
    });

    await waitFor(() => {
      expect(result.current.data?.pages[1]?.items).toEqual([
        expect.objectContaining({
          id: "workflow-2",
          name: "Campaign Health",
        }),
      ]);
    });
  });

  it("supports an explicit workspace override and stays idle without any workspace id", async () => {
    useWorkspaceStore.setState({
      currentWorkspace: null,
      workspaceList: [],
      sidebarCollapsed: false,
      isLoading: false,
    });

    const { Wrapper } = createHookWrapper();
    const enabledHook = renderHook(
      () => useWorkflowList({ workspaceId: "workspace-1", limit: 1 }),
      {
        wrapper: Wrapper,
      },
    );
    const disabledHook = renderHook(() => useWorkflowList(), {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(enabledHook.result.current.isSuccess).toBe(true);
    });

    expect(enabledHook.result.current.data?.pages[0]?.items[0]).toMatchObject({
      id: "workflow-1",
    });
    expect(disabledHook.result.current.fetchStatus).toBe("idle");
  });

  it("honors an explicit disabled flag even when a workspace is available", () => {
    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(
      () => useWorkflowList({ workspaceId: "workspace-1", enabled: false }),
      {
        wrapper: Wrapper,
      },
    );

    expect(result.current.fetchStatus).toBe("idle");
  });
});
