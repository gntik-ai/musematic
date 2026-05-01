import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import StatusSubscriptionsSettingsPage from "@/app/(main)/settings/status-subscriptions/page";
import { renderWithProviders } from "@/test-utils/render";
import { server } from "@/vitest.setup";
import type { StatusSubscription } from "@/lib/hooks/use-status-subscriptions";

const baseSubscription: StatusSubscription = {
  id: "sub-email-1",
  channel: "email",
  target: "ops@example.com",
  scope_components: [],
  health: "healthy",
  confirmed_at: "2026-05-01T10:00:00.000Z",
  created_at: "2026-05-01T09:00:00.000Z",
};

let subscriptions: StatusSubscription[];

describe("status subscription settings", () => {
  beforeEach(() => {
    subscriptions = [{ ...baseSubscription }];
    vi.spyOn(window, "confirm").mockReturnValue(true);
    server.use(
      http.get("*/api/v1/me/status-subscriptions", () =>
        HttpResponse.json({ items: subscriptions }),
      ),
      http.post("*/api/v1/me/status-subscriptions", async ({ request }) => {
        const payload = (await request.json()) as {
          channel: StatusSubscription["channel"];
          target: string;
          scope_components: string[];
        };
        const created: StatusSubscription = {
          id: "sub-created-1",
          channel: payload.channel,
          target: payload.target,
          scope_components: payload.scope_components,
          health: payload.channel === "email" ? "pending" : "healthy",
          confirmed_at:
            payload.channel === "email" ? null : "2026-05-01T10:05:00.000Z",
          created_at: "2026-05-01T10:05:00.000Z",
        };
        subscriptions = [...subscriptions, created];
        return HttpResponse.json(created, { status: 201 });
      }),
      http.patch("*/api/v1/me/status-subscriptions/:subscriptionId", async ({ params, request }) => {
        const payload = (await request.json()) as {
          target?: string;
          scope_components?: string[];
        };
        subscriptions = subscriptions.map((subscription) =>
          subscription.id === params.subscriptionId
            ? {
                ...subscription,
                target: payload.target ?? subscription.target,
                scope_components:
                  payload.scope_components ?? subscription.scope_components,
              }
            : subscription,
        );
        return HttpResponse.json(
          subscriptions.find((subscription) => subscription.id === params.subscriptionId),
        );
      }),
      http.delete("*/api/v1/me/status-subscriptions/:subscriptionId", ({ params }) => {
        subscriptions = subscriptions.filter(
          (subscription) => subscription.id !== params.subscriptionId,
        );
        return HttpResponse.json({ status: "unsubscribed", message: "Removed" });
      }),
    );
  });

  it("lists, adds, edits, and removes subscriptions", async () => {
    const user = userEvent.setup();
    renderWithProviders(<StatusSubscriptionsSettingsPage />);

    expect(await screen.findByText("ops@example.com")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Add Subscription" }));
    const dialog = screen.getByRole("dialog", { name: "Add status subscription" });
    await user.selectOptions(within(dialog).getByLabelText("Channel"), "webhook");
    await user.type(
      within(dialog).getByLabelText("Webhook URL"),
      "https://example.com/status-webhook",
    );
    await user.type(
      within(dialog).getByLabelText("Component scope"),
      "control-plane-api, reasoning-engine",
    );
    await user.click(within(dialog).getByRole("button", { name: "Add Subscription" }));

    expect(await screen.findByText("https://example.com/status-webhook")).toBeInTheDocument();
    expect(screen.getByText("control-plane-api, reasoning-engine")).toBeInTheDocument();

    await user.click(screen.getByLabelText("Edit webhook subscription"));
    const editDialog = screen.getByRole("dialog", { name: "Edit status subscription" });
    await user.clear(within(editDialog).getByLabelText("Target"));
    await user.type(
      within(editDialog).getByLabelText("Target"),
      "https://example.com/status-webhook-v2",
    );
    await user.clear(within(editDialog).getByLabelText("Component scope"));
    await user.type(within(editDialog).getByLabelText("Component scope"), "reasoning-engine");
    await user.click(within(editDialog).getByRole("button", { name: "Save" }));

    expect(await screen.findByText("https://example.com/status-webhook-v2")).toBeInTheDocument();
    expect(screen.getByText("reasoning-engine")).toBeInTheDocument();

    await user.click(screen.getByLabelText("Remove webhook subscription"));

    await waitFor(() => {
      expect(screen.queryByText("https://example.com/status-webhook-v2")).not.toBeInTheDocument();
    });
    expect(screen.getByText("ops@example.com")).toBeInTheDocument();
  });

  it("rolls back optimistic removal when the API delete fails", async () => {
    const user = userEvent.setup();
    server.use(
      http.delete("*/api/v1/me/status-subscriptions/:subscriptionId", async () => {
        await new Promise((resolve) => window.setTimeout(resolve, 50));
        return HttpResponse.json(
          {
            error: {
              code: "delete_failed",
              message: "Delete failed",
            },
          },
          { status: 500 },
        );
      }),
    );

    renderWithProviders(<StatusSubscriptionsSettingsPage />);

    expect(await screen.findByText("ops@example.com")).toBeInTheDocument();
    await user.click(screen.getByLabelText("Remove email subscription"));

    await waitFor(() => {
      expect(screen.queryByText("ops@example.com")).not.toBeInTheDocument();
    });
    expect(await screen.findByText("ops@example.com")).toBeInTheDocument();
  });
});
