import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function AuditPage() {
  return <GenericAdminSectionPage title="Audit Query" description="Unified audit search." help={<HelpContent />} />;
}
