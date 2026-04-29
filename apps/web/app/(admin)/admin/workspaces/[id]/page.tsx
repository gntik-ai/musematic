import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function WorkspaceDetailPage() {
  return <GenericAdminSectionPage title="Workspace Detail" description="Members, quotas, and activity." help={<HelpContent />} />;
}
