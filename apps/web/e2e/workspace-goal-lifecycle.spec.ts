import { expect, test } from "@playwright/test";
import {
  fulfillJson,
  installFrontendState,
  workspaceFixture,
} from "@/e2e/frontend-expansions/helpers";

const conversation = {
  id: "conversation-1",
  workspace_id: workspaceFixture.id,
  title: "Fraud triage",
  created_at: "2026-04-20T10:00:00.000Z",
  interactions: [
    {
      id: "interaction-1",
      conversation_id: "conversation-1",
      agent_id: "agent-1",
      agent_fqn: "ops:advisor",
      agent_display_name: "Ops Advisor",
      goal_id: "goal-1",
      state: "active",
      reasoning_mode: "chain_of_thought",
      self_correction_count: 0,
      created_at: "2026-04-20T10:00:00.000Z",
      updated_at: "2026-04-20T10:01:00.000Z",
    },
  ],
  branches: [],
};

const goalItems = {
  items: [
    {
      id: "goal-1",
      workspace_id: workspaceFixture.id,
      title: "Resolve fraud escalation",
      description: "Coordinate the fraud response path.",
      status: "in_progress",
      created_at: "2026-04-20T09:00:00.000Z",
      updated_at: "2026-04-20T10:00:00.000Z",
    },
  ],
  total: 1,
};

const interactionMessages = {
  items: [
    {
      id: "message-user-1",
      conversation_id: "conversation-1",
      interaction_id: "interaction-1",
      sender_type: "user",
      sender_id: "user-1",
      sender_display_name: "Operator",
      content: "Please review the payment anomaly.",
      attachments: [],
      status: "complete",
      is_mid_process_injection: false,
      branch_origin: null,
      created_at: "2026-04-20T10:00:00.000Z",
      updated_at: "2026-04-20T10:00:00.000Z",
    },
    {
      id: "message-agent-1",
      conversation_id: "conversation-1",
      interaction_id: "interaction-1",
      sender_type: "agent",
      sender_id: "agent-1",
      sender_display_name: "Ops Advisor",
      content: "Escalate the case and request enhanced verification.",
      attachments: [],
      status: "complete",
      is_mid_process_injection: false,
      branch_origin: null,
      created_at: "2026-04-20T10:01:00.000Z",
      updated_at: "2026-04-20T10:01:00.000Z",
    },
  ],
  next_cursor: null,
};

const goalMessages = {
  items: [
    {
      id: "goal-message-1",
      goal_id: "goal-1",
      sender_type: "agent",
      sender_id: "agent-1",
      sender_display_name: "Ops Advisor",
      agent_fqn: "ops:advisor",
      content: "Escalate the case and request enhanced verification.",
      originating_interaction_id: "interaction-1",
      created_at: "2026-04-20T10:01:00.000Z",
    },
  ],
  next_cursor: null,
};

test.beforeEach(async ({ page }) => {
  await installFrontendState(page, {
    roles: ["platform_admin", "workspace_admin", "agent_operator"],
    workspaceId: workspaceFixture.id,
  });

  await page.route("**/api/v1/conversations/conversation-1", async (route) => {
    await fulfillJson(route, conversation);
  });
  await page.route("**/api/v1/interactions/interaction-1/messages?**", async (route) => {
    await fulfillJson(route, interactionMessages);
  });
  await page.route("**/api/v1/workspaces/workspace-1/goals?page=1&page_size=20", async (route) => {
    await fulfillJson(route, goalItems);
  });
  await page.route("**/api/v1/workspaces/workspace-1/goals/goal-1/messages?**", async (route) => {
    await fulfillJson(route, goalMessages);
  });
  await page.route("**/api/v1/workspaces/workspace-1/goals/goal-1/messages/message-agent-1/rationale", async (route) => {
    await fulfillJson(route, {
      items: [
        {
          id: "rule-1",
          goal_id: "goal-1",
          message_id: "message-agent-1",
          agent_fqn: "ops:advisor",
          strategy_name: "tool-router",
          decision: "respond",
          score: 0.9,
          matched_terms: ["fraud", "escalation"],
          rationale: "Matched escalation policy and selected the investigation toolset.",
          error: null,
          created_at: "2026-04-20T10:02:00.000Z",
        },
        {
          id: "rule-2",
          goal_id: "goal-1",
          message_id: "message-agent-1",
          agent_fqn: "ops:advisor",
          strategy_name: "risk-check",
          decision: "warn",
          score: 0.2,
          matched_terms: [],
          rationale: "Manual review still required for high-value transfers.",
          error: null,
          created_at: "2026-04-20T10:02:30.000Z",
        },
      ],
      total: 2,
    });
  });
});

test("filters the conversation to goal-linked messages, opens rationale, and completes the goal", async ({ page }) => {
  let patchedStatus: string | null = null;
  await page.route("**/api/v1/workspaces/workspace-1/goals/goal-1", async (route) => {
    patchedStatus = String((route.request().postDataJSON() as Record<string, unknown>).status ?? "");
    await fulfillJson(route, {
      ...goalItems.items[0],
      status: "completed",
      updated_at: "2026-04-20T11:00:00.000Z",
    });
  });

  await page.goto("/conversations/conversation-1");

  await expect(page.getByText("Resolve fraud escalation")).toBeVisible();
  await expect(page.getByText("in progress")).toBeVisible();

  await page.getByLabel("Toggle goal-scoped filter").click();
  await expect(page).toHaveURL(/goal-scoped=true/);
  await expect(page.getByText("Filtered to goal: Resolve fraud escalation")).toBeVisible();
  await expect(page.getByText("Escalate the case and request enhanced verification.")).toBeVisible();

  await page.getByRole("button", { name: "Dismiss" }).click();
  await expect(page).not.toHaveURL(/goal-scoped=true/);

  await page.getByLabel("Inspect rationale for Ops Advisor message").click();
  await expect(page.getByText("Decision Rationale")).toBeVisible();
  for (const section of ["Tool choices", "Retrieved memories", "Risk flags", "Policy checks"]) {
    await expect(page.getByText(section)).toBeVisible();
  }
  await page.keyboard.press("Escape");
  await expect(page.getByText("Decision Rationale")).not.toBeVisible();

  await page.getByRole("button", { name: "Complete Goal" }).click();
  await expect(page.getByText("Complete active goal")).toBeVisible();
  await page.getByRole("button", { name: "Complete Goal" }).nth(1).click();

  await expect.poll(() => patchedStatus).toBe("completed");
});
