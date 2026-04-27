import Link from "next/link";
import { redirect } from "next/navigation";
import { OAuthProviderButtons } from "@/components/features/auth/OAuthProviderButtons";
import { SignupForm } from "@/components/features/auth/SignupForm";
import { Button } from "@/components/ui/button";

export default function SignupPage() {
  if (process.env.NEXT_PUBLIC_FEATURE_SIGNUP_ENABLED === "false") {
    redirect("/signup/disabled");
  }

  return (
    <div className="space-y-6">
      <SignupForm />
      <OAuthProviderButtons variant="signup" />
      <div className="text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Button asChild className="h-auto px-1 py-0" variant="ghost">
          <Link href="/login">Sign in</Link>
        </Button>
      </div>
    </div>
  );
}
