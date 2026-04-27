"use client";

import { useEffect } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";

interface CaptchaWidgetProps {
  onTokenChange: (token: string | null) => void;
}

export function CaptchaWidget({ onTokenChange }: CaptchaWidgetProps) {
  const provider = process.env.NEXT_PUBLIC_CAPTCHA_PROVIDER;

  useEffect(() => {
    if (provider === "hcaptcha" || provider === "turnstile") {
      onTokenChange(null);
    }
  }, [onTokenChange, provider]);

  if (!provider) {
    return null;
  }

  return (
    <Alert>
      <AlertDescription>
        CAPTCHA is configured for {provider}, but the provider widget is not installed in
        this build.
      </AlertDescription>
    </Alert>
  );
}
