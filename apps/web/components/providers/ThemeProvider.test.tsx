import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@/components/providers/ThemeProvider";

const { nextThemeSpy } = vi.hoisted(() => ({
  nextThemeSpy: vi.fn(({ children }: { children: React.ReactNode }) => (
    <div data-testid="next-themes-provider">{children}</div>
  )),
}));

vi.mock("next-themes", () => ({
  ThemeProvider: nextThemeSpy,
}));

describe("ThemeProvider", () => {
  it("forwards the expected next-themes configuration", () => {
    render(
      <ThemeProvider>
        <div>child</div>
      </ThemeProvider>,
    );

    expect(screen.getByText("child")).toBeInTheDocument();
    expect(nextThemeSpy).toHaveBeenCalled();
    expect(nextThemeSpy.mock.calls[0]?.[0]).toMatchObject({
      attribute: "class",
      defaultTheme: "system",
      disableTransitionOnChange: true,
      enableSystem: true,
    });
  });
});
