import { expect, test, type Page } from "@playwright/test";
import { mockAuthApi, signIn } from "@/e2e/auth/helpers";

/**
 * UPD-049 refresh (102) T031 — review-queue assignment + self-review gating.
 *
 * Asserts the frontend behaviour for the four interactions documented in
 * `specs/102-marketplace-scope/quickstart.md` Walkthroughs 1 and 2:
 *
 * 1. Lead opens the queue and assigns a submission to a reviewer.
 * 2. Filter chips narrow the queue (Unassigned / Assigned to me / All).
 * 3. Self-authored rows render the badge and disable Approve/Reject/Claim.
 * 4. Assigning to the submitter is refused client-side with an error
 *    (defense in depth — backend FR-741.9 enforces too).
 *
 * Backend is mocked at the network layer; this spec exercises only UI
 * affordances and TanStack Query wiring, not the live service.
 */

const QUEUE_URL = "**/api/v1/admin/marketplace-review/queue**";
const ASSIGN_URL = (id: string) =>
  `**/api/v1/admin/marketplace-review/${id}/assign`;

const SUBMITTER_ID = "00000000-0000-0000-0000-aaaaaaaaaaaa";
const ASSIGNEE_ID = "00000000-0000-0000-0000-bbbbbbbbbbbb";
const SELF_AGENT_ID = "11111111-1111-1111-1111-111111111111";
const NORMAL_AGENT_ID = "22222222-2222-2222-2222-222222222222";

const QUEUE_FIXTURE = {
  items: [
    {
      agent_id: NORMAL_AGENT_ID,
      agent_fqn: "finance-ops:kyc-verifier",
      tenant_slug: "default",
      submitter_user_id: SUBMITTER_ID,
      submitter_email: "alice@example.com",
      category: "automation",
      marketing_description: "Automates KYC.",
      tags: ["finance"],
      submitted_at: "2026-05-03T10:00:00Z",
      claimed_by_user_id: null,
      age_minutes: 30,
      assigned_reviewer_user_id: null,
      assigned_reviewer_email: null,
      is_self_authored: false,
    },
    {
      agent_id: SELF_AGENT_ID,
      agent_fqn: "ops:my-own-agent",
      tenant_slug: "default",
      submitter_user_id: SUBMITTER_ID,
      submitter_email: "self@example.com",
      category: "automation",
      marketing_description: "Created by current viewer.",
      tags: [],
      submitted_at: "2026-05-03T10:00:00Z",
      claimed_by_user_id: null,
      age_minutes: 30,
      assigned_reviewer_user_id: null,
      assigned_reviewer_email: null,
      is_self_authored: true,
    },
  ],
  next_cursor: null,
};

async function mockQueueApi(page: Page) {
  await page.route(QUEUE_URL, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(QUEUE_FIXTURE),
    });
  });
}

test.describe("Marketplace review queue — assignment & self-review", () => {
  test.beforeEach(async ({ page }) => {
    await mockAuthApi(page, { roles: ["platform_admin"] });
    await mockQueueApi(page);
    await signIn(page);
  });

  test("queue surfaces self-authored badge and assignment column", async ({
    page,
  }) => {
    await page.goto("/admin/marketplace-review");
    await expect(
      page.getByTestId(`self-authored-badge-${SELF_AGENT_ID}`),
    ).toBeVisible();
    await expect(
      page.getByTestId(`assigned-cell-${NORMAL_AGENT_ID}`),
    ).toContainText("—");
  });

  test("filter chips render and toggle the queue filter", async ({ page }) => {
    await page.goto("/admin/marketplace-review");
    const chips = page.getByTestId("review-queue-filter-chips");
    await expect(chips).toBeVisible();
    await page.getByTestId("queue-filter-chip-unassigned").click();
    await expect(page.getByTestId("queue-filter-chip-unassigned")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  test("approve/reject/claim buttons are disabled on self-authored rows", async ({
    page,
  }) => {
    await page.goto(`/admin/marketplace-review/${SELF_AGENT_ID}`);
    await expect(
      page.getByTestId("self-authored-detail-badge"),
    ).toBeVisible();
    await expect(page.getByTestId("approve-button")).toBeDisabled();
    await expect(page.getByTestId("reject-button")).toBeDisabled();
    await expect(page.getByTestId("claim-button")).toBeDisabled();
  });

  test("assigning the submitter is refused client-side", async ({ page }) => {
    await page.goto(`/admin/marketplace-review/${NORMAL_AGENT_ID}`);
    await page.getByTestId("assign-reviewer-button").click();
    await page
      .getByTestId("assign-reviewer-input")
      .fill(SUBMITTER_ID);
    await page.getByTestId("assign-reviewer-submit").click();
    await expect(page.getByTestId("assign-error")).toContainText(
      /author/i,
    );
  });

  test("assigning a different reviewer fires the assign mutation", async ({
    page,
  }) => {
    let assignBody: unknown = null;
    await page.route(ASSIGN_URL(NORMAL_AGENT_ID), async (route) => {
      assignBody = JSON.parse(route.request().postData() ?? "{}");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          agent_id: NORMAL_AGENT_ID,
          assigned_reviewer_user_id: ASSIGNEE_ID,
          assigned_reviewer_email: "reviewer@example.com",
          assigner_user_id: "00000000-0000-0000-0000-cccccccccccc",
          assigned_at: "2026-05-03T10:30:00Z",
          prior_assignee_user_id: null,
        }),
      });
    });
    await page.goto(`/admin/marketplace-review/${NORMAL_AGENT_ID}`);
    await page.getByTestId("assign-reviewer-button").click();
    await page.getByTestId("assign-reviewer-input").fill(ASSIGNEE_ID);
    await page.getByTestId("assign-reviewer-submit").click();
    await expect.poll(() => assignBody).toEqual({
      reviewer_user_id: ASSIGNEE_ID,
    });
  });
});
