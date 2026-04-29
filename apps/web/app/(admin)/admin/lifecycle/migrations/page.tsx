import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";

export default function MigrationsPage() {
  return <GenericAdminSectionPage title="Migrations" description="Alembic migration state and launch controls." superAdminOnly />;
}
