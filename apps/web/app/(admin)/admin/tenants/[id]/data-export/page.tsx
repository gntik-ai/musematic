import { AdminPage } from "@/components/features/admin/AdminPage";
import { TenantExportPanel } from "@/components/features/data-lifecycle/TenantExportPanel";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function TenantDataExportPage({ params }: PageProps) {
  const { id } = await params;

  return (
    <AdminPage
      title="Tenant data export"
      description="Generate a password-protected ZIP of all data owned by this tenant."
    >
      <TenantExportPanel tenantId={id} />
    </AdminPage>
  );
}
