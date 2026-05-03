import { AdminPage } from "@/components/features/admin/AdminPage";
import { DPAMetadataPanel } from "@/components/features/data-lifecycle/DPAMetadataPanel";

interface PageProps {
  params: Promise<{ tenantId: string }>;
}

export default async function TenantDPAPage({ params }: PageProps) {
  const { tenantId } = await params;

  return (
    <AdminPage
      title="Tenant DPA"
      description="Active Data Processing Agreement and Article 28 evidence for this tenant."
    >
      <DPAMetadataPanel tenantId={tenantId} />
    </AdminPage>
  );
}
