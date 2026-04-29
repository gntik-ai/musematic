import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function A2aIntegrationsPage() {
  return <GenericAdminSectionPage title="A2A Integrations" description="Agent-to-agent gateway configuration." help={<HelpContent />} />;
}
