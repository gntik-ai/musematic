import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function ExecutionsPage() {
  return <GenericAdminSectionPage title="Executions" description="Execution status and administrative controls." help={<HelpContent />} />;
}
