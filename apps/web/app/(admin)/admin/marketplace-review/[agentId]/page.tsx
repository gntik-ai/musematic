import { AdminPage } from "@/components/features/admin/AdminPage";
import { ReviewSubmissionDetail } from "@/components/features/marketplace/review/review-submission-detail";

/**
 * UPD-049 — Marketplace review submission detail page.
 *
 * Action surface: claim / release / approve / reject. The full marketing
 * description, tags, agent purpose, and submitter identity are surfaced
 * here so the reviewer has everything needed to make a decision.
 */
export default async function AdminMarketplaceReviewDetailPage({
  params,
}: {
  params: Promise<{ agentId: string }>;
}) {
  const { agentId } = await params;
  return (
    <AdminPage
      title="Review submission"
      description="Approve, reject, or hand back this public-marketplace submission."
    >
      <ReviewSubmissionDetail agentId={agentId} />
    </AdminPage>
  );
}
