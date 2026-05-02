import { AdminPage } from "@/components/features/admin/AdminPage";
import { SubscriptionDetailPanel } from "@/components/features/admin/SubscriptionDetailPanel";

interface SubscriptionDetailPageProps {
  params: Promise<{ id: string }>;
}

export default async function SubscriptionDetailPage({ params }: SubscriptionDetailPageProps) {
  const { id } = await params;

  return (
    <AdminPage
      title="Subscription detail"
      description="Status timeline, usage, current plan pinning, and lifecycle controls."
    >
      <SubscriptionDetailPanel id={id} />
    </AdminPage>
  );
}
