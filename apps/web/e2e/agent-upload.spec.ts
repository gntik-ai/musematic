import { expect, test } from "@playwright/test";
import {
  agentDetail,
  installAgentManagementState,
  mockAgentCatalogApi,
  mockAgentDetailApi,
  mockSlowUpload,
  mockSuccessfulUpload,
} from "@/e2e/agent-management/helpers";

test.beforeEach(async ({ page }) => {
  await installAgentManagementState(page);
  await mockAgentCatalogApi(page);
  await mockAgentDetailApi(page);
});

test("rejects invalid files inline", async ({ page }) => {
  await page.goto("/agent-management");
  await page.getByRole("button", { name: "Upload package" }).click();
  await page
    .locator('input[aria-label="Select package"]')
    .setInputFiles({
      name: "bad.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("bad"),
    });

  await expect(
    page.getByText("Unsupported file type. Only .tar.gz and .zip files are accepted."),
  ).toBeVisible();
});

test("uploads a valid package and routes to the draft detail page", async ({ page }) => {
  await mockSuccessfulUpload(page);
  await page.goto("/agent-management");
  await page.getByRole("button", { name: "Upload package" }).click();
  await page
    .locator('input[aria-label="Select package"]')
    .setInputFiles({
      name: "agent.tar.gz",
      mimeType: "application/gzip",
      buffer: Buffer.from("package"),
    });

  await expect(page.getByText("Uploading package…")).toBeVisible();
  await expect(page).toHaveURL(
    `/agent-management/${encodeURIComponent(agentDetail.fqn)}`,
  );
  await expect(page.getByRole("heading", { name: "KYC Monitor" })).toBeVisible();
});

test("allows cancelling an in-flight upload", async ({ page }) => {
  await mockSlowUpload(page);
  await page.goto("/agent-management");
  await page.getByRole("button", { name: "Upload package" }).click();
  await page
    .locator('input[aria-label="Select package"]')
    .setInputFiles({
      name: "agent.tar.gz",
      mimeType: "application/gzip",
      buffer: Buffer.from("package"),
    });

  await expect(page.getByText("Uploading package…")).toBeVisible();
  await page.getByRole("button", { name: "Cancel upload" }).click();
  await expect(page.getByText("Uploading package…")).not.toBeVisible();
});

