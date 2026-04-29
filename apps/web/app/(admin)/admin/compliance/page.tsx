import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function CompliancePage() {
  return <GenericAdminSectionPage title="Compliance" description="Control evidence and compliance posture." help={<HelpContent />} />;
}
