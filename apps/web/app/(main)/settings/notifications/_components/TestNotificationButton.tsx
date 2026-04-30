"use client";

import { useTranslations } from "next-intl";
import { Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useTestNotification } from "@/lib/hooks/use-me-notification-preferences";

export function TestNotificationButton({ eventType }: { eventType: string }) {
  const t = useTranslations("notifications.preferences.testEvents");
  const testNotification = useTestNotification();

  return (
    <Button
      size="sm"
      variant="outline"
      disabled={testNotification.isPending}
      onClick={() => testNotification.mutate(eventType)}
    >
      <Send className="h-4 w-4" />
      {t("button")}
    </Button>
  );
}
