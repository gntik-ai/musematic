import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function SessionsPage() {
  return <GenericAdminSectionPage title="Sessions" description="Active administrative sessions." help={<HelpContent />} />;
}
