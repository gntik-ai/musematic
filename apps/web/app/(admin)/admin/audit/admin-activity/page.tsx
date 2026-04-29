import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function AdminActivityPage() {
  return <GenericAdminSectionPage title="Admin Activity" description="Administrative audit events and diffs." help={<HelpContent />} />;
}
