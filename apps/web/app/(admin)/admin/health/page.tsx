import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function HealthPage() {
  return <GenericAdminSectionPage title="Health" description="Service health and live platform metrics." grafanaPath="d/platform-overview" help={<HelpContent />} />;
}
