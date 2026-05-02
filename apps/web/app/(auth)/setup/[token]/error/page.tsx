import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function SetupTokenErrorPage() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
          Invitation unavailable
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">Request a new invitation</h1>
        <p className="text-sm text-muted-foreground">
          This setup link can no longer be used.
        </p>
      </div>
      <Button asChild className="w-full" variant="outline">
        <Link href="/login">Back to login</Link>
      </Button>
    </div>
  );
}
