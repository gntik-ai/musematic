import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function McpIntegrationsPage() {
  return <GenericAdminSectionPage title="MCP Integrations" description="MCP server and tool catalog." help={<HelpContent />} />;
}
