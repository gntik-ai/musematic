import type { Page } from "@playwright/test";

export type A11ySurfaceGroup =
  | "auth"
  | "marketplace"
  | "agent-detail"
  | "workflow-editor"
  | "fleet-view"
  | "operator-dashboard"
  | "admin-settings"
  | "policies"
  | "trust"
  | "evaluation"
  | "costs"
  | "preferences"
  | "admin-locales";

export interface AuditedSurface {
  id: string;
  group: A11ySurfaceGroup;
  route: string;
  ready: (page: Page) => Promise<void>;
}

async function bodyReady(page: Page) {
  await page.locator("body").waitFor({ state: "visible" });
  await page.waitForLoadState("domcontentloaded");
}

export const auditedSurfaces: AuditedSurface[] = [
  { id: "login", group: "auth", route: "/login", ready: bodyReady },
  { id: "signup", group: "auth", route: "/signup", ready: bodyReady },
  { id: "dashboard", group: "marketplace", route: "/dashboard", ready: bodyReady },
  { id: "home", group: "marketplace", route: "/home", ready: bodyReady },
  { id: "marketplace", group: "marketplace", route: "/marketplace", ready: bodyReady },
  { id: "agent-detail", group: "agent-detail", route: "/marketplace/finance-ops/kyc-verifier", ready: bodyReady },
  { id: "agent-management", group: "agent-detail", route: "/agent-management", ready: bodyReady },
  { id: "workflow-editor", group: "workflow-editor", route: "/workflow-editor-monitor/new", ready: bodyReady },
  { id: "workflow-monitor", group: "workflow-editor", route: "/workflow-editor-monitor", ready: bodyReady },
  { id: "fleet-view", group: "fleet-view", route: "/fleet", ready: bodyReady },
  { id: "fleet-topology", group: "fleet-view", route: "/fleet/fleet-1", ready: bodyReady },
  { id: "operator-dashboard", group: "operator-dashboard", route: "/operator", ready: bodyReady },
  { id: "incidents", group: "operator-dashboard", route: "/operator/incidents", ready: bodyReady },
  { id: "regions", group: "operator-dashboard", route: "/operator?tab=regions", ready: bodyReady },
  { id: "maintenance", group: "operator-dashboard", route: "/operator?tab=maintenance", ready: bodyReady },
  { id: "capacity", group: "operator-dashboard", route: "/operator?tab=capacity", ready: bodyReady },
  { id: "admin-settings", group: "admin-settings", route: "/admin/settings", ready: bodyReady },
  { id: "policies", group: "policies", route: "/policies", ready: bodyReady },
  { id: "trust", group: "trust", route: "/trust", ready: bodyReady },
  { id: "trust-workbench", group: "trust", route: "/trust-workbench", ready: bodyReady },
  { id: "evaluation-runs", group: "evaluation", route: "/evaluation-testing", ready: bodyReady },
  { id: "conversations", group: "evaluation", route: "/conversations", ready: bodyReady },
  { id: "costs", group: "costs", route: "/costs", ready: bodyReady },
  { id: "preferences", group: "preferences", route: "/settings/preferences", ready: bodyReady },
  { id: "admin-locales", group: "admin-locales", route: "/admin/locales", ready: bodyReady },
];

export function surfacesForGroup(group: A11ySurfaceGroup): AuditedSurface[] {
  return auditedSurfaces.filter((surface) => surface.group === group);
}
