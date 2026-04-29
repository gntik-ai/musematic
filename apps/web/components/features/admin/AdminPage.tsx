import Link from "next/link";
import { AdminHelp } from "@/components/features/admin/AdminHelp";
import { cn } from "@/lib/utils";

interface AdminPageProps {
  title: string;
  description?: string | undefined;
  children: React.ReactNode;
  actions?: React.ReactNode | undefined;
  help?: React.ReactNode | undefined;
  className?: string | undefined;
}

export function AdminPage({
  title,
  description,
  children,
  actions,
  help,
  className,
}: AdminPageProps) {
  return (
    <section className={cn("space-y-4", className)}>
      <div className="flex flex-col gap-3 border-b pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <nav aria-label="Breadcrumb" className="mb-1 flex items-center gap-1 text-xs text-muted-foreground">
            <Link href="/admin" className="hover:text-primary">
              Admin
            </Link>
            <span>/</span>
            <span className="truncate">{title}</span>
          </nav>
          <h1 className="text-2xl font-semibold tracking-normal">{title}</h1>
          {description ? <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p> : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {help ? <AdminHelp>{help}</AdminHelp> : null}
          {actions}
        </div>
      </div>
      {children}
    </section>
  );
}
