import { AdminPage } from "@/components/features/admin/AdminPage";
import { TenantDeletionPanel } from "@/components/features/data-lifecycle/TenantDeletionPanel";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function TenantDeletePage({ params }: PageProps) {
  const { id } = await params;

  return (
    <AdminPage
      title="Tenant deletion"
      description="Two-phase cascade with 30-day grace, 2PA-gated and subscription-preflight enforced."
    >
      <TenantDeletionPanel tenantId={id} tenantSlug={id} />
    </AdminPage>
  );
}
