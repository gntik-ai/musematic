import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PerInteractionMuteToggle } from "@/components/features/alerts/per-interaction-mute-toggle";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";
import { renderWithProviders } from "@/test-utils/render";
import type { InteractionAlertMute, AlertRule } from "@/types/alerts";

const mutate = vi.fn();
let interactionMutes: InteractionAlertMute[] = [];
let rules: AlertRule[] = [];

vi.mock("@/lib/hooks/use-alert-rules", () => ({
  useAlertRules: () => ({
    interactionMutes,
    isLoading: false,
    rules,
  }),
  useAlertRulesMutations: () => ({
    isPending: false,
    mutate,
  }),
}));

describe("PerInteractionMuteToggle", () => {
  beforeEach(() => {
    mutate.mockClear();
    interactionMutes = [];
    rules = [
      {
        deliveryMethod: "in-app",
        enabled: true,
        id: "rule-1",
        transitionType: "execution.failed",
        userId: "user-1",
        workspaceId: "workspace-1",
      },
    ];
    useAuthStore.setState({
      user: {
        id: "user-1",
        email: "alex@musematic.dev",
        displayName: "Alex",
        avatarUrl: null,
        mfaEnrolled: true,
        roles: ["workspace_member"],
        workspaceId: "workspace-1",
      },
    } as never);
    useWorkspaceStore.setState({
      currentWorkspace: {
        id: "workspace-1",
        name: "Workspace One",
        slug: "workspace-one",
      },
    } as never);
  });

  it("creates a mute override when toggled on", async () => {
    const user = userEvent.setup();

    renderWithProviders(<PerInteractionMuteToggle interactionId="interaction-1" />);

    await user.click(
      screen.getByRole("button", { name: /mute alerts for this interaction/i }),
    );

    expect(mutate).toHaveBeenCalledWith({
      deliveryMethod: "in-app",
      interactionMutes: [
        expect.objectContaining({
          interactionId: "interaction-1",
          userId: "user-1",
        }),
      ],
      transitionTypes: ["execution.failed"],
    });
  });

  it("removes an existing mute override when toggled off", async () => {
    interactionMutes = [
      {
        interactionId: "interaction-1",
        mutedAt: "2026-04-20T08:40:00.000Z",
        userId: "user-1",
      },
    ];
    const user = userEvent.setup();

    renderWithProviders(<PerInteractionMuteToggle interactionId="interaction-1" />);

    await user.click(
      screen.getByRole("button", { name: /alerts muted for this interaction/i }),
    );

    expect(mutate).toHaveBeenCalledWith({
      deliveryMethod: "in-app",
      interactionMutes: [],
      transitionTypes: ["execution.failed"],
    });
  });
});
