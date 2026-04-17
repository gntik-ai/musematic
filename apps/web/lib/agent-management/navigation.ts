import { buildAgentManagementHref } from "@/lib/types/agent-management";

export function navigateToAgentDetail(fqn: string): void {
  if (typeof window === "undefined") {
    return;
  }

  window.location.assign(buildAgentManagementHref(fqn));
}
