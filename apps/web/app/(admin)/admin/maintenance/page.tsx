import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function MaintenancePage() {
  return <GenericAdminSectionPage title="Maintenance" description="Scheduled maintenance windows." help={<HelpContent />} />;
}
