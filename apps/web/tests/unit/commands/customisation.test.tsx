import { describe, expect, it } from "vitest";
import { validateShortcutBinding } from "@/components/layout/command-palette/CommandRegistry";

describe("shortcut customisation", () => {
  it("refuses browser-reserved shortcuts", () => {
    expect(validateShortcutBinding("Cmd+T")).toEqual({
      ok: false,
      reason: "That shortcut is reserved by the browser or operating system.",
    });
  });

  it("accepts application-owned shortcuts", () => {
    expect(validateShortcutBinding("Shift+L")).toEqual({ ok: true });
  });
});
