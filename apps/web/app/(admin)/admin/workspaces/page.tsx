import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function WorkspacesPage() {
  return <GenericAdminSectionPage title="Workspaces" description="Workspace inventory and status." help={<HelpContent />} />;
}
