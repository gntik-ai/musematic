import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function DlpPage() {
  return <GenericAdminSectionPage title="DLP Rules" description="Data loss prevention rules and overrides." help={<HelpContent />} />;
}
