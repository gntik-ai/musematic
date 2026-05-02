import { AdminPage } from "@/components/features/admin/AdminPage";
import { SubscriptionList } from "@/components/features/admin/SubscriptionList";

export default function AdminSubscriptionsPage() {
  return (
    <AdminPage
      title="Subscriptions"
      description="Cross-tenant subscription status, plan pins, and billing lifecycle actions."
    >
      <SubscriptionList />
    </AdminPage>
  );
}
