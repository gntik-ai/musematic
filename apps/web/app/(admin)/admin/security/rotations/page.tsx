import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function RotationsPage() {
  return <GenericAdminSectionPage title="Rotations" description="Secret rotation schedules." help={<HelpContent />} />;
}
