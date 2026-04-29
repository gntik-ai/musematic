import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function TenantDetailPage() {
  return <GenericAdminSectionPage title="Tenant Detail" description="Tenant users and workspaces." superAdminOnly help={<HelpContent />} />;
}
