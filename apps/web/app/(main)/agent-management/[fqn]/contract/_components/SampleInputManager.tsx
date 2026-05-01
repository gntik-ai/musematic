"use client";

import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";

export function SampleInputManager({ onLoad }: { onLoad: (value: string) => void }) {
  const t = useTranslations("creator.contract");

  return (
    <div className="flex gap-2">
      <Button
        size="sm"
        type="button"
        variant="outline"
        onClick={() => onLoad('{"output":{"answer":"ok"},"tokens":120}')}
      >
        {t("loadPassingSample")}
      </Button>
      <Button
        size="sm"
        type="button"
        variant="outline"
        onClick={() => onLoad('{"force_violation":true,"tokens":999999}')}
      >
        {t("loadViolationSample")}
      </Button>
    </div>
  );
}
