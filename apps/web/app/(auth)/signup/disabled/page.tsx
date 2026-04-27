import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function SignupDisabledPage() {
  const contactEmail =
    process.env.NEXT_PUBLIC_PLATFORM_ADMIN_CONTACT_EMAIL ?? "admin@example.com";

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
          Signup unavailable
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">
          Signups are currently disabled
        </h1>
        <p className="text-sm text-muted-foreground">
          Contact an administrator to request access to this platform.
        </p>
      </div>
      <div className="grid gap-3">
        <Button asChild>
          <a href={`mailto:${contactEmail}`}>Contact administrator</a>
        </Button>
        <Button asChild variant="outline">
          <Link href="/login">Back to login</Link>
        </Button>
      </div>
    </div>
  );
}
