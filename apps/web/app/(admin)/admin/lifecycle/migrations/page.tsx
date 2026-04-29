import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function MigrationsPage() {
  return <GenericAdminSectionPage title="Migrations" description="Alembic migration state and launch controls." superAdminOnly help={<HelpContent />} />;
}
