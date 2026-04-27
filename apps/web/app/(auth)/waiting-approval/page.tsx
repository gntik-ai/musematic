import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export default function WaitingApprovalPage() {
  const contactEmail =
    process.env.NEXT_PUBLIC_PLATFORM_ADMIN_CONTACT_EMAIL ?? "admin@example.com";
  const reviewTime =
    process.env.NEXT_PUBLIC_SIGNUP_APPROVAL_ESTIMATED_REVIEW_TIME ?? "one business day";

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <Badge variant="secondary">Pending approval</Badge>
        <h1 className="text-3xl font-semibold tracking-tight">Your account is under review</h1>
        <p className="text-sm text-muted-foreground">
          Administrators usually review signup requests within {reviewTime}.
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
