import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function PiaPage() {
  return <GenericAdminSectionPage title="PIA Reviews" description="Privacy impact assessment workflow." help={<HelpContent />} />;
}
