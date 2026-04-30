"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { ShieldCheck } from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useUserConsents } from "@/lib/hooks/use-me-consent";
import { ConsentCard } from "./_components/ConsentCard";
import { ConsentHistoryTab } from "./_components/ConsentHistoryTab";

export default function ConsentPage() {
  const t = useTranslations("privacy.consent");
  const [tab, setTab] = useState<"current" | "history">("current");
  const consents = useUserConsents();
  const items = consents.data?.items ?? [];

  return (
    <div className="mx-auto w-full max-w-5xl space-y-5">
      <div className="flex items-center gap-3">
        <ShieldCheck className="h-6 w-6 text-brand-accent" />
        <div>
          <h1 className="text-2xl font-semibold">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">{t("description")}</p>
        </div>
      </div>
      <Tabs>
        <TabsList>
          <TabsTrigger
            className={tab === "current" ? "bg-background shadow-sm" : ""}
            onClick={() => setTab("current")}
          >
            {t("tabs.current")}
          </TabsTrigger>
          <TabsTrigger
            className={tab === "history" ? "bg-background shadow-sm" : ""}
            onClick={() => setTab("history")}
          >
            {t("tabs.history")}
          </TabsTrigger>
        </TabsList>
        <TabsContent hidden={tab !== "current"}>
          <div className="space-y-3">
            {items.length === 0 ? (
              <div className="rounded-lg border border-border bg-card px-4 py-10 text-sm text-muted-foreground">
                {t("empty")}
              </div>
            ) : (
              items.map((item) => <ConsentCard key={item.id} consent={item} />)
            )}
          </div>
        </TabsContent>
        <TabsContent hidden={tab !== "history"}>
          <ConsentHistoryTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
