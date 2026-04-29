import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function ConsentPage() {
  return <GenericAdminSectionPage title="Consent Records" description="Consent inventory and revocation workflow." help={<HelpContent />} />;
}
