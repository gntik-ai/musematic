import { expect, type Page, type Route, test } from "@playwright/test";
import {
  installAgentManagementState,
  mockAgentCatalogApi,
} from "@/e2e/agent-management/helpers";

type SavedView = {
  id: string;
  owner_id: string;
  workspace_id: string | null;
  name: string;
  entity_type: string;
  filters: Record<string, unknown>;
  is_owner: boolean;
  is_shared: boolean;
  is_orphan_transferred: boolean;
  is_orphan: boolean;
  version: number;
  created_at: string;
  updated_at: string;
};

const now = "2026-04-29T08:00:00.000Z";

function savedView(overrides: Partial<SavedView>): SavedView {
  return {
    created_at: now,
    entity_type: "agent",
    filters: { labels: { env: "production" }, tags: ["production"] },
    id: "owner-view",
    is_orphan: false,
    is_orphan_transferred: false,
    is_owner: true,
    is_shared: false,
    name: "Production agents",
    owner_id: "user-1",
    updated_at: now,
    version: 1,
    workspace_id: "workspace-1",
    ...overrides,
  };
}

async function mockSavedViewApi(
  page: Page,
  views: SavedView[],
  createdPayloads: Record<string, unknown>[],
  shareEvents: Array<{ id: string; shared: boolean }>,
) {
  await page.route("**/api/v1/saved-views**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();

    if (method === "GET") {
      const entityType = url.searchParams.get("entity_type");
      await route.fulfill({
        body: JSON.stringify(views.filter((view) => view.entity_type === entityType)),
        contentType: "application/json",
        status: 200,
      });
      return;
    }

    if (method === "POST" && url.pathname.endsWith("/share")) {
      const id = url.pathname.split("/").at(-2) ?? "";
      shareEvents.push({ id, shared: true });
      const view = views.find((item) => item.id === id);
      if (view) {
        view.is_shared = true;
      }
      await route.fulfill({
        body: JSON.stringify(view),
        contentType: "application/json",
        status: 200,
      });
      return;
    }

    if (method === "POST" && url.pathname.endsWith("/unshare")) {
      const id = url.pathname.split("/").at(-2) ?? "";
      shareEvents.push({ id, shared: false });
      const view = views.find((item) => item.id === id);
      if (view) {
        view.is_shared = false;
      }
      await route.fulfill({
        body: JSON.stringify(view),
        contentType: "application/json",
        status: 200,
      });
      return;
    }

    if (method === "POST") {
      const payload = request.postDataJSON() as Record<string, unknown>;
      createdPayloads.push(payload);
      const created = savedView({
        entity_type: String(payload.entity_type),
        filters: payload.filters as Record<string, unknown>,
        id: "created-view",
        is_owner: true,
        is_shared: Boolean(payload.shared),
        name: String(payload.name),
        workspace_id: payload.workspace_id as string | null,
      });
      views.push(created);
      await route.fulfill({
        body: JSON.stringify(created),
        contentType: "application/json",
        status: 201,
      });
      return;
    }

    await route.fulfill({ status: 204 });
  });
}

async function mockPolicyApi(
  page: Page,
  createdPayloads: Record<string, unknown>[],
) {
  await page.route("**/api/v1/policies?**", async (route) => {
    await route.fulfill({
      body: JSON.stringify({
        items: [
          {
            current_version_id: "policy-version-1",
            description: "Blocks unsafe disclosure paths.",
            id: "policy-1",
            name: "Disclosure guardrail",
            scope_type: "workspace",
            status: "active",
            workspace_id: "workspace-1",
          },
        ],
        page: 1,
        page_size: 100,
        total: 1,
      }),
      contentType: "application/json",
      status: 200,
    });
  });

  await page.route("**/api/v1/policies", async (route) => {
    const payload = route.request().postDataJSON() as Record<string, unknown>;
    createdPayloads.push(payload);
    await route.fulfill({
      body: JSON.stringify({
        current_version_id: "policy-version-2",
        description: payload.description,
        id: "policy-2",
        name: payload.name,
        scope_type: "workspace",
        status: "active",
        workspace_id: payload.workspace_id,
      }),
      contentType: "application/json",
      status: 201,
    });
  });

  await page.route("**/api/v1/labels/expression/validate", async (route) => {
    const payload = route.request().postDataJSON() as { expression?: string };
    const expression = payload.expression ?? "";
    const isInvalid = expression.trim().endsWith("AND");
    await route.fulfill({
      body: JSON.stringify(
        isInvalid
          ? {
              error: {
                col: expression.length,
                line: 1,
                message: "Expected comparison",
                token: "<EOF>",
              },
              valid: false,
            }
          : { error: null, valid: true },
      ),
      contentType: "application/json",
      status: 200,
    });
  });
}

async function replaceMonacoValue(page: Page, value: string) {
  await page.waitForFunction(() => {
    type MonacoLike = {
      editor: { getModels: () => Array<{ setValue: (nextValue: string) => void }> };
    };
    return Boolean((window as Window & { monaco?: MonacoLike }).monaco?.editor.getModels().length);
  });
  await page.evaluate((nextValue) => {
    type MonacoLike = {
      editor: { getModels: () => Array<{ setValue: (nextValue: string) => void }> };
    };
    const monaco = (window as Window & { monaco?: MonacoLike }).monaco;
    const model = monaco?.editor.getModels()[0];
    if (!model) {
      throw new Error("Monaco model unavailable");
    }
    model.setValue(nextValue);
  }, value);
}

test("saved views apply URL filters, show shared/orphan indicators, and persist share state", async ({
  page,
}) => {
  const views = [
    savedView({ id: "owner-view" }),
    savedView({
      id: "orphan-view",
      is_orphan_transferred: true,
      is_owner: false,
      is_shared: true,
      name: "Former owner triage",
    }),
  ];
  const createdPayloads: Record<string, unknown>[] = [];
  const shareEvents: Array<{ id: string; shared: boolean }> = [];
  await installAgentManagementState(page);
  await mockAgentCatalogApi(page);
  await mockSavedViewApi(page, views, createdPayloads, shareEvents);

  await page.goto("/agent-management");

  await expect(page.getByLabel("Saved view")).toBeVisible();
  await expect(page.getByRole("option", { name: /Former owner triage/ })).toHaveText(
    /shared.*former member/,
  );

  await page.getByLabel("Saved view").selectOption("owner-view");
  await expect(page).toHaveURL(/tags=production/);
  await expect(page).toHaveURL(/label\.env=production/);

  await page.getByLabel("Toggle share").click();
  await expect.poll(() => shareEvents).toEqual([{ id: "owner-view", shared: true }]);

  await page.getByLabel("Save view").click();
  await page.getByLabel("Saved view name").fill("My filtered agents");
  await page.getByText("Share with workspace").click();
  await page.getByRole("button", { name: /^Save$/ }).click();

  await expect.poll(() => createdPayloads.at(-1)).toMatchObject({
    entity_type: "agent",
    name: "My filtered agents",
    shared: true,
    workspace_id: "workspace-1",
  });
});

test("policy label-expression editor validates invalid syntax before saving a valid rule", async ({
  page,
}) => {
  const createdPayloads: Record<string, unknown>[] = [];
  const views = [savedView({ entity_type: "policy", id: "policy-view" })];
  await installAgentManagementState(page);
  await mockSavedViewApi(page, views, [], []);
  await mockPolicyApi(page, createdPayloads);

  await page.goto("/policies");
  await expect(page.getByText("Disclosure guardrail")).toBeVisible();

  await page.getByRole("button", { name: "New Policy" }).click();
  await page.getByLabel("Policy name").fill("Production-only disclosure guardrail");
  await page.getByLabel("Policy description").fill("Applies only to production policy targets.");

  const editor = page.locator(".monaco-editor").first();
  await expect(editor).toBeVisible();
  await editor.click();
  await replaceMonacoValue(page, "env=production");
  await expect(page.getByText("Valid")).toBeVisible();

  await replaceMonacoValue(page, "env=production AND");
  await expect(page.getByText("1:18 Expected comparison")).toBeVisible();

  await replaceMonacoValue(page, "env=production AND tier=critical");
  await expect(page.getByText("Valid")).toBeVisible();
  await page.getByRole("button", { name: /^Save$/ }).click();

  await expect.poll(() => createdPayloads.at(-1)).toMatchObject({
    name: "Production-only disclosure guardrail",
    rules: { label_expression: "env=production AND tier=critical" },
    workspace_id: "workspace-1",
  });
});
