import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CommandPalette } from "@/components/layout/command-palette/CommandPalette";
import { CommandPaletteProvider, useCommandPalette } from "@/components/layout/command-palette/CommandPaletteProvider";
import { useRegisterCommands } from "@/components/layout/command-palette/CommandRegistry";
import { useAuthStore } from "@/store/auth-store";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

function RegisteredCommands() {
  const { setOpen } = useCommandPalette();
  useRegisterCommands([
    {
      id: "marketplace.search",
      label: "Search marketplace",
      category: "Marketplace",
      shortcut: "/",
      href: "/marketplace",
      keywords: ["agent"],
    },
  ]);
  return <button onClick={() => setOpen(true)}>Open</button>;
}

describe("command registry", () => {
  it("groups registered route commands and fuzzy-filters candidates", () => {
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

    render(
      <CommandPaletteProvider>
        <RegisteredCommands />
        <CommandPalette />
      </CommandPaletteProvider>,
    );

    fireEvent.click(screen.getByText("Open"));
    fireEvent.change(screen.getByTestId("command-input"), { target: { value: "agent" } });
    fireEvent.click(screen.getByText("Search marketplace"));

    expect(push).toHaveBeenCalledWith("/marketplace");
  });
});
