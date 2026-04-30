"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { KeyRound, ShieldCheck } from "lucide-react";

import { MfaEnrollmentDialog } from "@/components/features/auth/mfa-enrollment/MfaEnrollmentDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuthStore } from "@/store/auth-store";

export default function MfaSettingsPage() {
  const t = useTranslations("security.mfa");
  const user = useAuthStore((state) => state.user);
  const setUser = useAuthStore((state) => state.setUser);
  const [enrollOpen, setEnrollOpen] = useState(false);
  const enrolled = user?.mfaEnrolled ?? false;

  return (
    <div className="mx-auto w-full max-w-4xl space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <ShieldCheck className="h-6 w-6 text-brand-accent" />
          <div>
            <h1 className="text-2xl font-semibold">{t("title")}</h1>
            <p className="text-sm text-muted-foreground">{t("description")}</p>
          </div>
        </div>
        <Badge variant={enrolled ? "default" : "secondary"}>
          {enrolled ? t("status.active") : t("status.notEnrolled")}
        </Badge>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <KeyRound className="h-4 w-4 text-brand-accent" />
            {t("statusTitle")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            {enrolled ? t("activeDescription") : t("notEnrolledDescription")}
          </p>
          <div className="flex flex-wrap gap-2">
            {!enrolled ? (
              <Button onClick={() => setEnrollOpen(true)}>
                <ShieldCheck className="h-4 w-4" />
                {t("enroll")}
              </Button>
            ) : (
              <>
                <Button disabled variant="outline">
                  {t("regenerateBackupCodes")}
                </Button>
                <Button disabled variant="outline">
                  {t("disable")}
                </Button>
              </>
            )}
          </div>
        </CardContent>
      </Card>

      <MfaEnrollmentDialog
        onEnrolled={() => {
          if (user) {
            setUser({ ...user, mfaEnrolled: true });
          }
          setEnrollOpen(false);
        }}
        open={enrollOpen}
      />
    </div>
  );
}
