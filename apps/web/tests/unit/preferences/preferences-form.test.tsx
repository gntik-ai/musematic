import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PreferencesForm } from "@/components/features/preferences";
import { preferencesFormSchema } from "@/components/features/preferences/preferences-schema";
import { useUpdatePreferences, useUserPreferences } from "@/lib/api/preferences";
import { useWorkspaces } from "@/lib/hooks/use-workspaces";

const mutateAsync = vi.fn();
const setTheme = vi.fn();

vi.mock("next-themes", () => ({
  useTheme: () => ({ setTheme }),
}));

vi.mock("@/lib/api/preferences", () => ({
  useUserPreferences: vi.fn(),
  useUpdatePreferences: vi.fn(),
}));

vi.mock("@/lib/hooks/use-workspaces", () => ({
  useWorkspaces: vi.fn(),
}));

describe("PreferencesForm", () => {
  beforeEach(() => {
    mutateAsync.mockReset();
    mutateAsync.mockResolvedValue({});
    vi.mocked(useUserPreferences).mockReturnValue({
      data: {
        id: "prefs-1",
        user_id: "user-1",
        default_workspace_id: null,
        theme: "system",
        language: "en",
        timezone: "UTC",
        notification_preferences: {},
        data_export_format: "json",
        is_persisted: true,
        created_at: null,
        updated_at: null,
      },
    } as never);
    vi.mocked(useUpdatePreferences).mockReturnValue({
      mutateAsync,
      isPending: false,
    } as never);
    vi.mocked(useWorkspaces).mockReturnValue({
      workspaces: [
        {
          id: "11111111-1111-1111-1111-111111111111",
          name: "Risk Ops",
          slug: "risk-ops",
          description: null,
          memberCount: 8,
          createdAt: "2026-04-10T09:00:00.000Z",
        },
      ],
    } as never);
  });

  it("validates enum fields with Zod", () => {
    expect(
      preferencesFormSchema.safeParse({
        theme: "neon",
        language: "en",
        timezone: "UTC",
        default_workspace_id: null,
        data_export_format: "json",
        notification_preferences: {
          email: true,
          in_app: true,
          mobile_push: false,
          quiet_hours_start: "22:00",
          quiet_hours_end: "07:00",
        },
      }).success,
    ).toBe(false);
  });

  it("saves preferences with explicit Save and applies the selected theme", async () => {
    render(<PreferencesForm />);

    fireEvent.click(screen.getByTestId("theme-picker-dark"));
    fireEvent.change(screen.getByLabelText("Language"), { target: { value: "es" } });
    fireEvent.change(screen.getByLabelText("Time zone"), { target: { value: "Europe/Madrid" } });
    fireEvent.click(screen.getByRole("button", { name: /save preferences/i }));

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          theme: "dark",
          language: "es",
          timezone: "Europe/Madrid",
        }),
      );
    });
    expect(setTheme).toHaveBeenCalledWith("dark");
  });
});
