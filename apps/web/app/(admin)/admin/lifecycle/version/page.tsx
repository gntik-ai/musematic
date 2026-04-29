import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function VersionPage() {
  return <GenericAdminSectionPage title="Version" description="Release metadata by component." superAdminOnly help={<HelpContent />} />;
}
