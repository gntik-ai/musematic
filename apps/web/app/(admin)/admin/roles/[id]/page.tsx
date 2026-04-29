import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function RoleDetailPage() {
  return <GenericAdminSectionPage title="Role Detail" description="Permission diff and role assignment." help={<HelpContent />} />;
}
