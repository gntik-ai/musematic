import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function TenantsPage() {
  return <GenericAdminSectionPage title="Tenants" description="Platform tenant inventory." superAdminOnly help={<HelpContent />} />;
}
