import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { QuotasTab } from "@/components/features/admin/tabs/QuotasTab";
import { renderWithProviders } from "@/test-utils/render";
import { setPlatformAdminUser } from "@/tests/features/admin/test-helpers";
import { server } from "@/vitest.setup";

describe("QuotasTab", () => {
  beforeEach(() => {
    setPlatformAdminUser();
  });

  it("pre-populates default quotas and loads workspace override data from the combobox", async () => {
    const user = userEvent.setup();

    renderWithProviders(<QuotasTab />);

    const maxAgentInputs = await screen.findAllByLabelText("Max agents");
    expect(maxAgentInputs[0]).toHaveValue(100);

    await user.click(
      screen.getByRole("button", { name: "Select workspace override target" }),
    );
    await user.type(screen.getByLabelText("Search workspaces"), "Signal");
    await user.click(screen.getByRole("button", { name: /Signal Lab/i }));

    await waitFor(() => {
      const overrideInputs = screen.getAllByLabelText("Max agents");
      expect(overrideInputs[1]).toHaveValue(250);
    });
  });

  it("sends null fields correctly when saving a workspace override", async () => {
    const user = userEvent.setup();
    let capturedBody: unknown;

    server.use(
      http.patch(
        "*/api/v1/admin/settings/quotas/workspaces/:workspaceId",
        async ({ request }) => {
          capturedBody = await request.json();
          return HttpResponse.json({
            workspace_id: "workspace-1",
            workspace_name: "Signal Lab",
            ...(capturedBody as Record<string, unknown>),
            updated_at: "2026-04-12T12:00:00.000Z",
          });
        },
      ),
    );

    renderWithProviders(<QuotasTab />);

    await user.click(
      screen.getByRole("button", { name: "Select workspace override target" }),
    );
    await user.type(screen.getByLabelText("Search workspaces"), "Signal");
    await user.click(screen.getByRole("button", { name: /Signal Lab/i }));

    await waitFor(() => {
      expect(screen.getAllByLabelText("Max agents")[1]).toHaveValue(250);
    });

    await user.clear(screen.getAllByLabelText("Max agents")[1]);
    await user.clear(screen.getAllByLabelText("Storage quota (GB)")[1]);
    await user.type(screen.getAllByLabelText("Storage quota (GB)")[1], "640");
    await user.click(screen.getAllByRole("button", { name: "Save" })[1]);

    await waitFor(() => {
      expect(capturedBody).toEqual(
        expect.objectContaining({
          max_agents: null,
          storage_quota_gb: 640,
        }),
      );
    });
  });
});
