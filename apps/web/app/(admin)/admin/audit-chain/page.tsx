import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function AuditChainPage() {
  return <GenericAdminSectionPage title="Audit Chain" description="Integrity verification and signed exports." help={<HelpContent />} />;
}
