import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function WorkspaceQuotasPage() {
  return <GenericAdminSectionPage title="Workspace Quotas" description="Agent, fleet, execution, storage, and cost limits." help={<HelpContent />} />;
}
