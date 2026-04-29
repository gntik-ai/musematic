import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function RunbooksPage() {
  return <GenericAdminSectionPage title="Runbooks" description="Operational runbook library." help={<HelpContent />} />;
}
