import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function RunbookDetailPage() {
  return <GenericAdminSectionPage title="Runbook Detail" description="Steps, owners, and execution history." help={<HelpContent />} />;
}
