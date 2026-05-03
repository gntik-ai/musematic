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
  | "admin-locales"
  | "self-service"
  | "workspace-owner"
  | "creator-uis";

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
  // UPD-049 refresh (102) T064 — assignment + publish surfaces.
  { id: "marketplace-review", group: "admin-settings", route: "/admin/marketplace-review", ready: bodyReady },
  { id: "agent-publish-flow", group: "agent-detail", route: "/agent-management/finance-ops%3Akyc-verifier/publish", ready: bodyReady },
  // UPD-050 refresh (103) T087 — abuse-prevention admin surfaces.
  { id: "abuse-prevention", group: "admin-settings", route: "/admin/security/abuse-prevention", ready: bodyReady },
  { id: "abuse-suspensions", group: "admin-settings", route: "/admin/security/suspensions", ready: bodyReady },
  { id: "abuse-email-overrides", group: "admin-settings", route: "/admin/security/email-overrides", ready: bodyReady },
  { id: "abuse-geo-policy", group: "admin-settings", route: "/admin/security/geo-policy", ready: bodyReady },
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
  { id: "admin-settings-workspaces", group: "workspace-owner", route: "/admin/settings?tab=workspaces", ready: bodyReady },
  { id: "admin-settings-connectors", group: "workspace-owner", route: "/admin/settings?tab=connectors", ready: bodyReady },
  { id: "admin-settings-ibor", group: "workspace-owner", route: "/admin/settings?tab=ibor", ready: bodyReady },
  { id: "admin-settings-oauth-config", group: "admin-settings", route: "/admin/settings?tab=oauth&provider_tab=configuration", ready: bodyReady },
  { id: "admin-settings-oauth-status", group: "admin-settings", route: "/admin/settings?tab=oauth&provider_tab=status", ready: bodyReady },
  { id: "admin-settings-oauth-role-mappings", group: "admin-settings", route: "/admin/settings?tab=oauth&provider_tab=role-mappings", ready: bodyReady },
  { id: "admin-settings-oauth-history", group: "admin-settings", route: "/admin/settings?tab=oauth&provider_tab=history", ready: bodyReady },
  { id: "admin-settings-oauth-rate-limits", group: "admin-settings", route: "/admin/settings?tab=oauth&provider_tab=rate-limits", ready: bodyReady },
  { id: "policies", group: "policies", route: "/policies", ready: bodyReady },
  { id: "trust", group: "trust", route: "/trust", ready: bodyReady },
  { id: "trust-workbench", group: "trust", route: "/trust-workbench", ready: bodyReady },
  { id: "evaluation-runs", group: "evaluation", route: "/evaluation-testing", ready: bodyReady },
  { id: "conversations", group: "evaluation", route: "/conversations", ready: bodyReady },
  { id: "costs", group: "costs", route: "/costs", ready: bodyReady },
  { id: "preferences", group: "preferences", route: "/settings/preferences", ready: bodyReady },
  { id: "admin-locales", group: "admin-locales", route: "/admin/locales", ready: bodyReady },
  { id: "notifications-inbox", group: "self-service", route: "/notifications", ready: bodyReady },
  {
    id: "notification-preferences",
    group: "self-service",
    route: "/settings/notifications",
    ready: bodyReady,
  },
  { id: "api-keys", group: "self-service", route: "/settings/api-keys", ready: bodyReady },
  { id: "security-overview", group: "self-service", route: "/settings/security", ready: bodyReady },
  { id: "security-mfa", group: "self-service", route: "/settings/security/mfa", ready: bodyReady },
  {
    id: "security-sessions",
    group: "self-service",
    route: "/settings/security/sessions",
    ready: bodyReady,
  },
  {
    id: "security-activity",
    group: "self-service",
    route: "/settings/security/activity",
    ready: bodyReady,
  },
  {
    id: "privacy-consent",
    group: "self-service",
    route: "/settings/privacy/consent",
    ready: bodyReady,
  },
  { id: "privacy-dsr", group: "self-service", route: "/settings/privacy/dsr", ready: bodyReady },
  { id: "workspaces-list", group: "workspace-owner", route: "/workspaces", ready: bodyReady },
  { id: "workspace-dashboard", group: "workspace-owner", route: "/workspaces/workspace-1", ready: bodyReady },
  { id: "workspace-members", group: "workspace-owner", route: "/workspaces/workspace-1/members", ready: bodyReady },
  { id: "workspace-settings", group: "workspace-owner", route: "/workspaces/workspace-1/settings", ready: bodyReady },
  { id: "workspace-connectors", group: "workspace-owner", route: "/workspaces/workspace-1/connectors", ready: bodyReady },
  {
    id: "workspace-connector-detail",
    group: "workspace-owner",
    route: "/workspaces/workspace-1/connectors/connector-1",
    ready: bodyReady,
  },
  { id: "workspace-quotas", group: "workspace-owner", route: "/workspaces/workspace-1/quotas", ready: bodyReady },
  { id: "workspace-tags", group: "workspace-owner", route: "/workspaces/workspace-1/tags", ready: bodyReady },
  { id: "workspace-visibility", group: "workspace-owner", route: "/workspaces/workspace-1/visibility", ready: bodyReady },
  {
    id: "creator-context-profile",
    group: "creator-uis",
    route: "/agent-management/creator-ui%3Aagent/context-profile",
    ready: bodyReady,
  },
  {
    id: "creator-context-profile-history",
    group: "creator-uis",
    route: "/agent-management/creator-ui%3Aagent/context-profile/history",
    ready: bodyReady,
  },
  {
    id: "creator-contract",
    group: "creator-uis",
    route: "/agent-management/creator-ui%3Aagent/contract",
    ready: bodyReady,
  },
  {
    id: "creator-contract-history",
    group: "creator-uis",
    route: "/agent-management/creator-ui%3Aagent/contract/history",
    ready: bodyReady,
  },
  {
    id: "creator-contract-library",
    group: "creator-uis",
    route: "/agent-management/contracts/library",
    ready: bodyReady,
  },
];

export function surfacesForGroup(group: A11ySurfaceGroup): AuditedSurface[] {
  return auditedSurfaces.filter((surface) => surface.group === group);
}
