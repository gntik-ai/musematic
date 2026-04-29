import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function DsrPage() {
  return <GenericAdminSectionPage title="DSR Queue" description="Privacy request review and execution." help={<HelpContent />} />;
}
