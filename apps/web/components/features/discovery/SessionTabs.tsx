"use client";

import Link from "next/link";
import { FlaskConical, Lightbulb, Network, SearchCheck, ScrollText } from "lucide-react";
import { Tabs, TabsList } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

const tabs = [
  { href: "", label: "Overview", icon: SearchCheck },
  { href: "hypotheses", label: "Hypotheses", icon: Lightbulb },
  { href: "experiments", label: "Experiments", icon: FlaskConical },
  { href: "evidence", label: "Evidence", icon: ScrollText },
  { href: "network", label: "Network", icon: Network },
] as const;

export function SessionTabs({
  sessionId,
  active,
}: {
  sessionId: string;
  active: "overview" | "hypotheses" | "experiments" | "evidence" | "network";
}) {
  return (
    <Tabs>
      <TabsList className="flex flex-wrap">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const href = tab.href
            ? `/discovery/${encodeURIComponent(sessionId)}/${tab.href}`
            : `/discovery/${encodeURIComponent(sessionId)}`;
          const tabActive = active === (tab.href || "overview");
          return (
            <Link
              className={cn(
                "inline-flex items-center rounded-md px-3 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                tabActive ? "bg-background text-foreground shadow-sm" : "text-muted-foreground",
              )}
              href={href}
              key={tab.label}
            >
              <Icon className="mr-2 h-4 w-4" />
              {tab.label}
            </Link>
          );
        })}
      </TabsList>
    </Tabs>
  );
}
