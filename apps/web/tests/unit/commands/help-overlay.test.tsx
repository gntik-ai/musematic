import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CommandPaletteProvider } from "@/components/layout/command-palette/CommandPaletteProvider";
import { useRegisterCommands } from "@/components/layout/command-palette/CommandRegistry";

function RegisteredCommands() {
  useRegisterCommands([
    {
      id: "platform.theme",
      label: "Cambiar tema",
      category: "Plataforma",
      shortcut: "Shift+T",
    },
  ]);
  return <input aria-label="Search" />;
}

describe("help overlay", () => {
  it("opens with ? only when focus is outside editable controls", () => {
    render(
      <CommandPaletteProvider>
        <RegisteredCommands />
      </CommandPaletteProvider>,
    );

    screen.getByLabelText("Search").focus();
    fireEvent.keyDown(screen.getByLabelText("Search"), { key: "?" });
    expect(screen.queryByRole("dialog", { name: /keyboard shortcuts/i })).not.toBeInTheDocument();

    screen.getByLabelText("Search").blur();
    fireEvent.keyDown(window, { key: "?" });

    expect(screen.getByRole("dialog", { name: /keyboard shortcuts/i })).toBeInTheDocument();
    expect(screen.getByText("Cambiar tema")).toBeInTheDocument();
  });
});
