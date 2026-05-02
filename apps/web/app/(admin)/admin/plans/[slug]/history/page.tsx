import { AdminPage } from "@/components/features/admin/AdminPage";
import { PlanVersionHistory } from "@/components/features/admin/PlanVersionHistory";

interface PlanHistoryPageProps {
  params: Promise<{ slug: string }>;
}

export default async function PlanHistoryPage({ params }: PlanHistoryPageProps) {
  const { slug } = await params;

  return (
    <AdminPage
      title="Plan history"
      description="Published versions, deprecation state, subscription counts, and parameter diffs."
    >
      <PlanVersionHistory slug={slug} />
    </AdminPage>
  );
}
