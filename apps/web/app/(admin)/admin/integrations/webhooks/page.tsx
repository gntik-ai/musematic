import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function WebhooksPage() {
  return <GenericAdminSectionPage title="Webhooks" description="Outbound webhook integrations." help={<HelpContent />} />;
}
