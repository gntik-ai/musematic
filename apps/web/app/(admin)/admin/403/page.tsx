import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function AdminForbiddenPage() {
  return (
    <main className="flex min-h-[60vh] items-center justify-center px-4">
      <div className="max-w-md rounded-md border bg-card p-6 text-center">
        <h1 className="text-xl font-semibold">Super admin role required</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          This page is available only to platform-wide administrators.
        </p>
        <Button asChild className="mt-4">
          <Link href="/admin">Admin</Link>
        </Button>
      </div>
    </main>
  );
}
