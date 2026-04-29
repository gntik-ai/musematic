import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function LogRetentionPage() {
  return <GenericAdminSectionPage title="Log Retention" description="Log retention and storage policy." help={<HelpContent />} />;
}
