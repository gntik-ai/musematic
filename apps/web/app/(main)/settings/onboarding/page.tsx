"use client";

import { RotateCcw } from "lucide-react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { useOnboarding } from "@/lib/hooks/use-onboarding";

export default function OnboardingSettingsPage() {
  const router = useRouter();
  const onboarding = useOnboarding();

  return (
    <div className="max-w-2xl space-y-5">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Onboarding</h1>
        <p className="text-sm text-muted-foreground">
          Reopen the first-run workspace guide.
        </p>
      </div>
      <Button
        disabled={onboarding.relaunch.isPending}
        type="button"
        onClick={() =>
          void onboarding.relaunch.mutateAsync(undefined).then(() => router.push("/onboarding"))
        }
      >
        <RotateCcw className="h-4 w-4" />
        Re-launch wizard
      </Button>
    </div>
  );
}
