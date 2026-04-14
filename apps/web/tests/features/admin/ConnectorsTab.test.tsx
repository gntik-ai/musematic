import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import * as adminHooks from "@/lib/hooks/use-admin-settings";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConnectorsTab } from "@/components/features/admin/tabs/ConnectorsTab";
import { renderWithProviders } from "@/test-utils/render";
import { setPlatformAdminUser } from "@/tests/features/admin/test-helpers";
import { server } from "@/vitest.setup";

describe("ConnectorsTab", () => {
  beforeEach(() => {
    setPlatformAdminUser();
  });

  it("renders all connector cards", async () => {
    renderWithProviders(<ConnectorsTab />);

    expect(await screen.findByText("Slack")).toBeInTheDocument();
    expect(screen.getByText("Telegram")).toBeInTheDocument();
    expect(screen.getByText("Webhook")).toBeInTheDocument();
    expect(screen.getByText("Email")).toBeInTheDocument();
  });

  it("optimistically toggles and rolls back on API failure", async () => {
    const user = userEvent.setup();

    server.use(
      http.patch("*/api/v1/admin/settings/connectors/email", async () => {
        await new Promise((resolve) => window.setTimeout(resolve, 50));
        return HttpResponse.json(
          {
            error: {
              code: "connector_update_failed",
              message: "Unable to disable connector",
            },
          },
          { status: 500 },
        );
      }),
    );

    renderWithProviders(<ConnectorsTab />);

    const toggle = await screen.findByRole("switch", { name: "Toggle Email" });
    expect(toggle).toHaveAttribute("aria-checked", "true");

    await user.click(toggle);

    await waitFor(() => {
      expect(toggle).toHaveAttribute("aria-checked", "false");
    });

    await waitFor(() => {
      expect(toggle).toHaveAttribute("aria-checked", "true");
    });
  });

  it("shows a warning when a disabled connector still has active instances", async () => {
    server.use(
      http.get("*/api/v1/admin/settings/connectors", () =>
        HttpResponse.json([
          {
            slug: "email",
            display_name: "Email",
            description: "Email delivery connectors.",
            is_enabled: false,
            active_instance_count: 3,
            max_payload_size_bytes: 26214,
            default_retry_count: 2,
            updated_at: "2026-04-12T12:00:00.000Z",
          },
        ]),
      ),
    );

    renderWithProviders(<ConnectorsTab />);

    expect(await screen.findByText("3 active instances")).toBeInTheDocument();
  });

  it("shows loading skeleton cards while connector configs are pending", () => {
    const hookSpy = vi.spyOn(adminHooks, "useConnectorTypeConfigs").mockReturnValue({
      data: undefined,
      isLoading: true,
    } as never);

    renderWithProviders(<ConnectorsTab />);

    expect(document.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);

    hookSpy.mockRestore();
  });
});
