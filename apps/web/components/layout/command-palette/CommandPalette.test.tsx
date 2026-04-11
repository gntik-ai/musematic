import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CommandPalette } from "@/components/layout/command-palette/CommandPalette";
import { CommandPaletteProvider } from "@/components/layout/command-palette/CommandPaletteProvider";
import { useAuthStore } from "@/store/auth-store";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

describe("CommandPalette", () => {
  beforeEach(() => {
    push.mockReset();
    useAuthStore.setState({
      user: {
        id: "user-1",
        email: "ops@musematic.dev",
        displayName: "Ops",
        avatarUrl: null,
        roles: ["workspace_admin", "agent_operator"],
        workspaceId: "workspace-1",
      },
    } as never);
  });

  it("opens with the keyboard shortcut and filters items", () => {
    render(
      <CommandPaletteProvider>
        <CommandPalette />
      </CommandPaletteProvider>,
    );

    fireEvent.keyDown(window, { ctrlKey: true, key: "k" });
    const input = screen.getByTestId("command-input");
    expect(input).toBeInTheDocument();

    fireEvent.change(input, { target: { value: "agent" } });
    fireEvent.click(screen.getByText("Agents"));

    expect(push).toHaveBeenCalledWith("/agents");
  });
});
