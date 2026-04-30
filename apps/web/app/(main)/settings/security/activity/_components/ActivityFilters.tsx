"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { SlidersHorizontal } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface ActivityFiltersProps {
  values: {
    eventType: string;
    start: string;
    end: string;
  };
}

export function ActivityFilters({ values }: ActivityFiltersProps) {
  const t = useTranslations("security.activity.filters");
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  function update(key: string, value: string) {
    const next = new URLSearchParams(searchParams.toString());
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    router.replace(`${pathname}?${next.toString()}`);
  }

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="h-4 w-4 text-brand-accent" />
          <h2 className="text-sm font-semibold">{t("title")}</h2>
        </div>
        <Button size="sm" variant="ghost" onClick={() => router.replace(pathname)}>
          {t("reset")}
        </Button>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <div className="space-y-2">
          <Label htmlFor="activity-event">{t("eventType")}</Label>
          <Input
            id="activity-event"
            value={values.eventType}
            onChange={(event) => update("eventType", event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="activity-start">{t("start")}</Label>
          <Input
            id="activity-start"
            type="date"
            value={values.start}
            onChange={(event) => update("start", event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="activity-end">{t("end")}</Label>
          <Input
            id="activity-end"
            type="date"
            value={values.end}
            onChange={(event) => update("end", event.target.value)}
          />
        </div>
      </div>
    </div>
  );
}
