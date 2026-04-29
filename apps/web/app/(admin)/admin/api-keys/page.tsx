import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function ApiKeysPage() {
  return <GenericAdminSectionPage title="API Keys" description="Service account credentials." help={<HelpContent />} />;
}
