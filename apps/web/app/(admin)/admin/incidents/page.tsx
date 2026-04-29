import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function IncidentsPage() {
  return <GenericAdminSectionPage title="Incidents" description="Open incidents and response state." help={<HelpContent />} />;
}
