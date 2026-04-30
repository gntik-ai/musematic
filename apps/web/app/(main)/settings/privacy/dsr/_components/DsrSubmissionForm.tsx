"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { FilePlus2 } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { useSubmitDSR } from "@/lib/hooks/use-me-dsr";
import type { UserDsrSubmitRequest } from "@/lib/schemas/me";

const requestTypes: UserDsrSubmitRequest["request_type"][] = [
  "access",
  "rectification",
  "erasure",
  "portability",
  "restriction",
  "objection",
];

export function DsrSubmissionForm() {
  const t = useTranslations("privacy.dsr.submit");
  const submit = useSubmitDSR();
  const [requestType, setRequestType] = useState<UserDsrSubmitRequest["request_type"]>("access");
  const [legalBasis, setLegalBasis] = useState("");
  const [confirmText, setConfirmText] = useState("");

  function submitRequest() {
    submit.mutate({
      request_type: requestType,
      legal_basis: legalBasis || null,
      hold_hours: 0,
      confirm_text: confirmText || null,
    });
  }

  const erasure = requestType === "erasure";

  return (
    <div className="space-y-4 rounded-lg border border-border bg-card p-4">
      <div>
        <h2 className="text-sm font-semibold">{t("title")}</h2>
        <p className="text-sm text-muted-foreground">{t("description")}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="dsr-type">{t("requestType")}</Label>
          <Select
            id="dsr-type"
            value={requestType}
            onChange={(event) => setRequestType(event.target.value as UserDsrSubmitRequest["request_type"])}
          >
            {requestTypes.map((type) => (
              <option key={type} value={type}>
                {t(`types.${type}`)}
              </option>
            ))}
          </Select>
        </div>
        {erasure ? (
          <div className="space-y-2">
            <Label htmlFor="dsr-confirm">{t("confirmDelete")}</Label>
            <Input
              id="dsr-confirm"
              value={confirmText}
              onChange={(event) => setConfirmText(event.target.value)}
            />
          </div>
        ) : null}
      </div>
      {erasure ? (
        <Alert variant="destructive">
          <AlertTitle>{t("erasureTitle")}</AlertTitle>
          <AlertDescription>
            {t("erasureDescription")}
          </AlertDescription>
        </Alert>
      ) : null}
      <div className="space-y-2">
        <Label htmlFor="dsr-basis">{t("legalBasis")}</Label>
        <Textarea
          id="dsr-basis"
          value={legalBasis}
          onChange={(event) => setLegalBasis(event.target.value)}
        />
      </div>
      <Button
        disabled={submit.isPending || (erasure && confirmText !== "DELETE")}
        onClick={submitRequest}
      >
        <FilePlus2 className="h-4 w-4" />
        {t("submit")}
      </Button>
    </div>
  );
}
