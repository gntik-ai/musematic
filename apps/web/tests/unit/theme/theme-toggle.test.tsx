import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeToggle } from "@/components/layout/theme-toggle/ThemeToggle";
import { useUpdatePreferences } from "@/lib/api/preferences";

const setTheme = vi.fn();
const mutateAsync = vi.fn();

vi.mock("next-themes", () => ({
  useTheme: () => ({
    theme: "system",
    resolvedTheme: "light",
    setTheme,
  }),
}));

vi.mock("@/lib/api/preferences", () => ({
  useUpdatePreferences: vi.fn(),
}));

describe("ThemeToggle", () => {
  beforeEach(() => {
    setTheme.mockReset();
    mutateAsync.mockReset();
    mutateAsync.mockResolvedValue({});
    vi.mocked(useUpdatePreferences).mockReturnValue({
      mutateAsync,
      isPending: false,
    } as never);
  });

  it("lists all four themes and persists the selected theme", async () => {
    render(<ThemeToggle />);

    fireEvent.click(screen.getByTestId("theme-toggle"));

    expect(screen.getByTestId("theme-option-light")).toBeInTheDocument();
    expect(screen.getByTestId("theme-option-dark")).toBeInTheDocument();
    expect(screen.getByTestId("theme-option-system")).toBeInTheDocument();
    expect(screen.getByTestId("theme-option-high_contrast")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("theme-option-high_contrast"));

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith({ theme: "high_contrast" });
    });
    expect(setTheme).toHaveBeenCalledWith("high_contrast");
  });

  it("rolls back optimistic theme selection on PATCH failure", async () => {
    mutateAsync.mockRejectedValueOnce(new Error("nope"));
    render(<ThemeToggle />);

    fireEvent.click(screen.getByTestId("theme-toggle"));
    fireEvent.click(screen.getByTestId("theme-option-dark"));

    await waitFor(() => {
      expect(setTheme).toHaveBeenCalledWith("system");
    });
  });
});
