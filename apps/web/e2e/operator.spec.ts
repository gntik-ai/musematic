import { expect, test } from "@playwright/test";
import {
  emitOperatorAlert,
  installOperatorState,
  mockOperatorApi,
} from "@/e2e/operator/helpers";

test.beforeEach(async ({ page }) => {
  await installOperatorState(page);
  await mockOperatorApi(page);
});

test("renders the operator dashboard and completes the drill-down navigation flow", async ({
  page,
}) => {
  await page.goto("/operator");
  await emitOperatorAlert(page);

  await expect(
    page.getByRole("heading", { name: "Operator Dashboard" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Active Executions", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Queued Steps", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Pending Approvals", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Recent Failures (1h)", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Avg Latency (p50)", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Fleet Health Score", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Service health", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("PostgreSQL")).toBeVisible();
  await expect(page.getByText("Simulation Controller")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Alert feed", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Critical runtime-controller/i }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Agent attention", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Queue backlog", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Reasoning budget", exact: true }),
  ).toBeVisible();

  await page.getByLabel("Open execution exec-run-0001").click();
  await expect(page).toHaveURL("/operator/executions/exec-run-0001");
  await expect(
    page.getByRole("heading", { name: "Execution Drill-Down" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Trajectory", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Checkpoints", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Debate", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "ReAct", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Trajectory", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Checkpoints", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Checkpoints", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Debate", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Debate transcript", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "ReAct", exact: true }).click();
  await expect(page.getByRole("heading", { name: "ReAct cycles", exact: true })).toBeVisible();

  await page
    .locator("main")
    .getByRole("link", { name: "Operator", exact: true })
    .click();
  await expect(page).toHaveURL("/operator");
  await expect(
    page.getByRole("heading", { name: "Operator Dashboard" }),
  ).toBeVisible();
});
