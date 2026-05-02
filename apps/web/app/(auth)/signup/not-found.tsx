import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function SignupNotFound() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">Page not found</h1>
        <p className="text-sm text-muted-foreground">
          The requested page could not be found.
        </p>
      </div>
      <Button asChild className="w-full" variant="outline">
        <Link href="/login">Back to login</Link>
      </Button>
    </div>
  );
}
