import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function RolesPage() {
  return <GenericAdminSectionPage title="Roles" description="Role permissions and assignments." help={<HelpContent />} />;
}
