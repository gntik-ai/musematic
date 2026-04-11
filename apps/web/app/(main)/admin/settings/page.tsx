import { AdminSettingsPanel } from "@/components/features/admin/AdminSettingsPanel";

interface AdminSettingsPageProps {
  searchParams?: {
    tab?: string | string[];
  };
}

export default function AdminSettingsPage({
  searchParams,
}: AdminSettingsPageProps) {
  const rawTab = Array.isArray(searchParams?.tab)
    ? searchParams?.tab[0]
    : searchParams?.tab;

  return <AdminSettingsPanel defaultTab={rawTab ?? "users"} />;
}
