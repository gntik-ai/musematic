import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function UserDetailPage() {
  return <GenericAdminSectionPage title="User Detail" description="Roles, sessions, and audit entries." help={<HelpContent />} />;
}
