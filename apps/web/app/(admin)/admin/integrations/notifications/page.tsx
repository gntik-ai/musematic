import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function NotificationIntegrationsPage() {
  return <GenericAdminSectionPage title="Notification Integrations" description="Email, Slack, SMS, Teams, and webhooks." help={<HelpContent />} />;
}
