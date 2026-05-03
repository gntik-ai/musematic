import { AdminPage } from "@/components/features/admin/AdminPage";
import { SuspensionDetail } from "@/components/features/admin-security/suspension-detail";

/**
 * UPD-050 — Suspension detail page. Rendered as an AdminPage with the
 * `SuspensionDetail` client component fetching evidence and offering
 * the lift action.
 */
export default async function AdminSuspensionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <AdminPage
      title="Suspension detail"
      description="Review evidence and lift the suspension if warranted."
    >
      <SuspensionDetail suspensionId={id} />
    </AdminPage>
  );
}
