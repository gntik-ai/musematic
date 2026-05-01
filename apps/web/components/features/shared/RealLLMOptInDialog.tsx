"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

export function RealLLMOptInDialog({
  disabled,
  onConfirm,
}: {
  disabled?: boolean;
  onConfirm: () => void;
}) {
  const t = useTranslations("creator.contract");
  const [confirmation, setConfirmation] = useState("");
  const [open, setOpen] = useState(false);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button disabled={disabled} type="button" variant="outline">
          {t("realLlmPreview")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("confirmRealLlmPreview")}</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          {t("realLlmCostWarning")}
        </p>
        <Input
          placeholder={t("useRealLlmConfirmation")}
          value={confirmation}
          onChange={(event) => setConfirmation(event.target.value)}
        />
        <DialogFooter>
          <Button
            disabled={confirmation !== "USE_REAL_LLM"}
            type="button"
            onClick={() => {
              onConfirm();
              setOpen(false);
              setConfirmation("");
            }}
          >
            {t("confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
