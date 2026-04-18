"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

const tabs = [
  { href: "/evaluation-testing", label: "Eval Suites", matches: (pathname: string) => !pathname.startsWith("/evaluation-testing/simulations") },
  { href: "/evaluation-testing/simulations", label: "Simulations", matches: (pathname: string) => pathname.startsWith("/evaluation-testing/simulations") },
] as const;

export default function EvaluationTestingLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();

  return (
    <Tabs className="space-y-6">
      <TabsList className="flex w-full justify-start gap-2 bg-transparent p-0">
        {tabs.map((tab) => {
          const active = tab.matches(pathname);
          return (
            <TabsTrigger
              key={tab.href}
              className={cn(
                "border border-border/70 bg-card px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground",
                active && "bg-primary text-primary-foreground hover:text-primary-foreground",
              )}
            >
              <Link href={tab.href}>{tab.label}</Link>
            </TabsTrigger>
          );
        })}
      </TabsList>
      <TabsContent className="mt-0">{children}</TabsContent>
    </Tabs>
  );
}
