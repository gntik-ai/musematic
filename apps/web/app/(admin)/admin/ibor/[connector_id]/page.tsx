import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function IborDetailPage() {
  return <GenericAdminSectionPage title="IBOR Connector" description="Sync history and mappings." help={<HelpContent />} />;
}
