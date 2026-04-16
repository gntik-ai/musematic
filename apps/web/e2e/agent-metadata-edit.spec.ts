import { expect, test } from "@playwright/test";
import {
  agentDetail,
  installAgentManagementState,
  mockAgentCatalogApi,
  mockAgentDetailApi,
  mockMetadataSaveApi,
} from "@/e2e/agent-management/helpers";

test.beforeEach(async ({ page }) => {
  await installAgentManagementState(page);
  await mockAgentCatalogApi(page);
  await mockAgentDetailApi(page);
  await mockMetadataSaveApi(page);
});

test("edit metadata, update the FQN preview, save successfully, and surface stale conflicts", async ({
  page,
}) => {
  await page.goto(
    `/agent-management/${encodeURIComponent(agentDetail.fqn)}?tab=metadata`,
  );

  await expect(page.getByRole("heading", { name: "KYC Monitor" })).toBeVisible();

  await page.getByLabel("Purpose").fill("");
  await expect(page.getByText("Purpose must be at least 20 characters")).toBeVisible();

  await page.getByLabel("Namespace").selectOption("ops");
  await page.getByLabel("Local name").fill("fraud-sentinel");
  await expect(page.getByText("Preview: ops:fraud-sentinel")).toBeVisible();

  await page
    .getByLabel("Purpose")
    .fill("Monitor transaction anomalies, route cases, and keep the fraud team informed.");

  await page.getByRole("button", { name: "Save metadata" }).click();
  await expect(page.getByText("Metadata updated")).toBeVisible();

  await page.getByLabel("Description").fill("Second save to trigger a stale conflict.");
  await page.getByRole("button", { name: "Save metadata" }).click();
  await expect(page.getByText("Stale settings detected")).toBeVisible();
});

