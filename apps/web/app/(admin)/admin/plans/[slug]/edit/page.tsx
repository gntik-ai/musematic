import { AdminPage } from "@/components/features/admin/AdminPage";
import { PlanEditForm } from "@/components/features/admin/PlanEditForm";

interface PlanEditPageProps {
  params: Promise<{ slug: string }>;
}

export default async function PlanEditPage({ params }: PlanEditPageProps) {
  const { slug } = await params;

  return (
    <AdminPage
      title="Edit plan"
      description="Publish a new immutable plan version from the current parameters."
    >
      <PlanEditForm slug={slug} />
    </AdminPage>
  );
}
