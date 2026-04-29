import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function FeatureFlagsPage() {
  return <GenericAdminSectionPage title="Feature Flags" description="Scoped feature flag overrides." help={<HelpContent />} />;
}
