import { expect, test } from "@playwright/test";
import {
  disconnectFrontendWs,
  emitFrontendWsEvent,
  fulfillJson,
  installFrontendState,
  installFrontendWs,
} from "@/e2e/frontend-expansions/helpers";

const initialAlerts = [
  {
    id: "alert-1",
    alert_type: "execution.failed",
    title: "Execution failed",
    body: "Primary execution failed.",
    read: false,
    interaction_id: null,
    source_reference: { url: "/operator" },
    created_at: "2026-04-20T10:00:00.000Z",
  },
];

test.beforeEach(async ({ page }) => {
  await installFrontendState(page, {
    roles: ["platform_admin", "workspace_admin", "agent_operator"],
  });
  await installFrontendWs(page);

  await page.route("**/me/alerts?**", async (route) => {
    await fulfillJson(route, { items: initialAlerts, total_unread: 1 });
  });
  await page.route("**/me/alerts/unread-count", async (route) => {
    await fulfillJson(route, { count: 1 });
  });

  let savedSettings = {
    id: "settings-1",
    user_id: "user-1",
    state_transitions: [
      "execution.failed",
      "trust.certification_expired",
      "governance.verdict_issued",
      "interaction.idle",
    ],
    delivery_method: "in_app",
    interaction_mutes: [] as Array<{ interaction_id: string; muted_at: string; user_id: string }>,
  };

  await page.route("**/me/alert-settings", async (route) => {
    if (route.request().method() === "PUT") {
      const payload = route.request().postDataJSON() as Record<string, unknown>;
      savedSettings = {
        ...savedSettings,
        state_transitions: Array.isArray(payload.state_transitions)
          ? payload.state_transitions.map(String)
          : [],
        delivery_method: String(payload.delivery_method ?? "in_app") as "in_app",
        interaction_mutes: Array.isArray(payload.interaction_mutes)
          ? payload.interaction_mutes.map((entry) => ({
              interaction_id: String((entry as Record<string, unknown>).interaction_id),
              muted_at: String((entry as Record<string, unknown>).muted_at),
              user_id: String((entry as Record<string, unknown>).user_id ?? "user-1"),
            }))
          : savedSettings.interaction_mutes,
      };
      await fulfillJson(route, savedSettings);
      return;
    }

    await fulfillJson(route, savedSettings);
  });

  await page.route("**/api/v1/conversations/conversation-1", async (route) => {
    await fulfillJson(route, {
      id: "conversation-1",
      workspace_id: "workspace-1",
      title: "Goal-linked conversation",
      created_at: "2026-04-20T10:00:00.000Z",
      interactions: [
        {
          id: "interaction-1",
          conversation_id: "conversation-1",
          agent_id: "agent-1",
          agent_fqn: "ops:advisor",
          agent_display_name: "Ops Advisor",
          goal_id: null,
          state: "active",
          reasoning_mode: "none",
          self_correction_count: 0,
          created_at: "2026-04-20T10:00:00.000Z",
          updated_at: "2026-04-20T10:00:00.000Z",
        },
      ],
      branches: [],
    });
  });
  await page.route("**/api/v1/interactions/interaction-1/messages?**", async (route) => {
    await fulfillJson(route, { items: [], next_cursor: null });
  });
  await page.route("**/api/v1/workspaces/workspace-1/goals?page=1&page_size=20", async (route) => {
    await fulfillJson(route, { items: [], total: 0 });
  });
});

test("saves alert settings, increments the bell from WS, mutes one interaction, and reconciles after reconnect", async ({ page }) => {
  await page.goto("/settings/alerts");

  await expect(page.getByText(/Recommended defaults keep high-signal failures/i)).toBeVisible();
  await expect(page.getByText("execution.failed")).toBeVisible();
  await expect(page.getByText("trust.certification_expired")).toBeVisible();
  await expect(page.getByText("governance.verdict_issued")).toBeVisible();

  const interactionIdleRow = page
    .getByText("interaction.idle")
    .locator("..")
    .locator("..");
  await interactionIdleRow.getByRole("switch").click();
  await page.getByLabel("Delivery method").selectOption("in-app");
  await page.getByRole("button", { name: "Save alert settings" }).click();

  const bell = page.getByLabel("Notifications");
  await expect(bell).toContainText("1");

  await emitFrontendWsEvent(page, {
    channel: "alerts",
    type: "alert.created",
    timestamp: new Date().toISOString(),
    payload: {
      id: "alert-2",
      severity: "critical",
      source_service: "runtime-controller",
      message: "Warm pool fell behind target",
      description: "Just now",
      interaction_id: "interaction-2",
    },
  });

  await expect(bell).toContainText("2");
  await bell.click();
  await expect(page.getByText(/2 unread/i)).toBeVisible();

  await page.goto("/conversations/conversation-1");
  const muteToggle = page.getByRole("button", {
    name: /Mute alerts for this interaction/i,
  });
  await expect(muteToggle).toBeEnabled();
  await muteToggle.click();
  await expect(
    page.getByRole("button", { name: /Alerts muted for this interaction/i }),
  ).toBeVisible();

  await emitFrontendWsEvent(page, {
    channel: "alerts",
    type: "alert.created",
    timestamp: new Date().toISOString(),
    payload: {
      id: "alert-3",
      severity: "warning",
      source_service: "conversation-service",
      message: "Muted interaction alert",
      interaction_id: "interaction-1",
    },
  });

  await expect(bell).toContainText("1");

  await page.getByLabel("Notifications").click();
  await disconnectFrontendWs(page);

  await page.reload();
  await page.getByLabel("Notifications").click();
  await expect(page.getByText(/1 unread/)).toBeVisible();
});
