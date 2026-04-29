import { AdminPage } from "@/components/features/admin/AdminPage";
import { AdminSettingsPanel } from "@/components/features/admin/AdminSettingsPanel";
import { HelpContent } from "./help";

interface AdminSettingsPageProps {
  searchParams?: Promise<{ tab?: string | string[] }>;
}

export default async function AdminSettingsPage({ searchParams }: AdminSettingsPageProps) {
  const resolvedSearchParams = await searchParams;
  const rawTab = Array.isArray(resolvedSearchParams?.tab)
    ? resolvedSearchParams.tab[0]
    : resolvedSearchParams?.tab;

  return (
    <AdminPage
      title="Settings"
      description="Platform settings, access policies, quotas, connectors, email, and security."
      help={<HelpContent />}
    >
      <AdminSettingsPanel defaultTab={rawTab ?? "users"} renderHeading={false} />
    </AdminPage>
  );
}
