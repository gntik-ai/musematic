import { AdminSettingsPanel } from "@/components/features/admin/AdminSettingsPanel";

interface AdminSettingsPageProps {
  searchParams?: Promise<{ tab?: string | string[] }>;
}

export default async function AdminSettingsPage({ searchParams }: AdminSettingsPageProps) {
  const resolvedSearchParams = await searchParams;
  const rawTab = Array.isArray(resolvedSearchParams?.tab)
    ? resolvedSearchParams.tab[0]
    : resolvedSearchParams?.tab;

  return <AdminSettingsPanel defaultTab={rawTab ?? "users"} />;
}
