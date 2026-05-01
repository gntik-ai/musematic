import { AdminPage } from "@/components/features/admin/AdminPage";
import { TenantDetailPanel } from "@/components/features/admin/TenantDetailPanel";
import { HelpContent } from "./help";

interface TenantDetailPageProps {
  params: Promise<{ id: string }>;
}

export default async function TenantDetailPage({ params }: TenantDetailPageProps) {
  const { id } = await params;

  return (
    <AdminPage
      title="Tenant detail"
      description="Tenant identity, contract metadata, DPA state, and lifecycle controls."
      help={<HelpContent />}
    >
      <TenantDetailPanel tenantId={id} />
    </AdminPage>
  );
}
