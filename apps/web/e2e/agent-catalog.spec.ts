import { expect, test } from "@playwright/test";
import {
  agentDetail,
  installAgentManagementState,
  mockAgentCatalogApi,
  mockAgentDetailApi,
} from "@/e2e/agent-management/helpers";

test.beforeEach(async ({ page }) => {
  await installAgentManagementState(page);
  await mockAgentCatalogApi(page);
  await mockAgentDetailApi(page);
});

test("browse the catalog, search, filter by maturity, and navigate to detail", async ({
  page,
}) => {
  await page.goto("/agent-management");

  await expect(page.getByText("KYC Monitor")).toBeVisible();
  await expect(page.getByText("Case Triage")).toBeVisible();

  await page.getByLabel("Search agents").fill("kyc");
  await expect(page.getByText("KYC Monitor")).toBeVisible();
  await expect(page.getByText("Case Triage")).not.toBeVisible();

  await page.getByLabel("Search agents").fill("");
  await page.getByLabel("Maturity").selectOption("production");
  await expect(page.getByText("KYC Monitor")).toBeVisible();
  await expect(page.getByText("Case Triage")).not.toBeVisible();

  await page.getByText("KYC Monitor").click();

  await expect(page).toHaveURL(
    `/agent-management/${encodeURIComponent(agentDetail.fqn)}`,
  );
  await expect(page.getByRole("heading", { name: "KYC Monitor" })).toBeVisible();
});

