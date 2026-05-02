import { AdminPage } from "@/components/features/admin/AdminPage";
import { ReviewQueueShell } from "@/components/features/marketplace/review/review-queue-shell";

/**
 * UPD-049 — Platform-staff marketplace review queue.
 * Endpoint: `/api/v1/admin/marketplace-review/queue` (super-admin only).
 */
export default function AdminMarketplaceReviewPage() {
  return (
    <AdminPage
      title="Marketplace review"
      description="Cross-tenant queue of pending public-marketplace submissions awaiting platform-staff review."
    >
      <ReviewQueueShell />
    </AdminPage>
  );
}
