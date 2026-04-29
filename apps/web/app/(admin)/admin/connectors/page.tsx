import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function ConnectorsPage() {
  return <GenericAdminSectionPage title="Connectors" description="Connector configuration and credential rotation." help={<HelpContent />} />;
}
