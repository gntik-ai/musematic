import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function OAuthProvidersPage() {
  return <GenericAdminSectionPage title="OAuth Providers" description="Identity provider configuration." help={<HelpContent />} />;
}
