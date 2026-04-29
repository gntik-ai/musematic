"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ShieldCheck, Users, UserPlus2, Gauge, PlugZap, Mail, Lock, KeyRound } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { UsersTab } from "@/components/features/admin/tabs/UsersTab";
import { SignupPolicyTab } from "@/components/features/admin/tabs/SignupPolicyTab";
import { QuotasTab } from "@/components/features/admin/tabs/QuotasTab";
import { ConnectorsTab } from "@/components/features/admin/tabs/ConnectorsTab";
import { EmailTab } from "@/components/features/admin/tabs/EmailTab";
import { SecurityTab } from "@/components/features/admin/tabs/SecurityTab";
import { OAuthProviderAdminPanel } from "@/components/features/auth/OAuthProviderAdminPanel";

const tabs = [
  { value: "users", label: "Users", icon: Users, component: UsersTab },
  {
    value: "signup",
    label: "Signup",
    icon: UserPlus2,
    component: SignupPolicyTab,
  },
  { value: "quotas", label: "Quotas", icon: Gauge, component: QuotasTab },
  {
    value: "connectors",
    label: "Connectors",
    icon: PlugZap,
    component: ConnectorsTab,
  },
  { value: "email", label: "Email", icon: Mail, component: EmailTab },
  {
    value: "oauth",
    label: "OAuth Providers",
    icon: KeyRound,
    component: OAuthProviderAdminPanel,
  },
  { value: "security", label: "Security", icon: Lock, component: SecurityTab },
] as const;

type AdminTabValue = (typeof tabs)[number]["value"];

function isAdminTabValue(value: string): value is AdminTabValue {
  return tabs.some((tab) => tab.value === value);
}

export function AdminSettingsPanel({
  defaultTab,
  renderHeading = true,
}: {
  defaultTab: string;
  renderHeading?: boolean;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [currentTab, setCurrentTab] = useState<AdminTabValue>(() => {
    return isAdminTabValue(defaultTab) ? defaultTab : "users";
  });

  useEffect(() => {
    setCurrentTab(isAdminTabValue(defaultTab) ? defaultTab : "users");
  }, [defaultTab]);

  const ActiveTab = tabs.find((tab) => tab.value === currentTab)?.component ?? UsersTab;

  return (
    <div className="space-y-6">
      {renderHeading ? (
        <section className="space-y-2">
          <div
            className={[
              "flex items-center gap-2 text-sm font-semibold uppercase",
              "tracking-[0.2em] text-brand-accent",
            ].join(" ")}
          >
            <ShieldCheck className="h-4 w-4" />
            Platform administration
          </div>
          <div>
            <h1 className="text-3xl font-semibold">Admin settings</h1>
            <p className="mt-2 max-w-3xl text-muted-foreground">
              Manage global access policies, quotas, connectors, email delivery,
              and platform security.
            </p>
          </div>
        </section>
      ) : null}

      <Tabs>
        <TabsList className="flex w-full flex-col gap-2 rounded-2xl bg-muted/70 p-2 md:flex-row">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const active = currentTab === tab.value;

            return (
              <TabsTrigger
                key={tab.value}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center justify-center gap-2 px-4 py-2.5",
                  "focus-visible:ring-2 focus-visible:ring-ring",
                  active
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:bg-background/60 hover:text-foreground",
                )}
                onClick={() => {
                  setCurrentTab(tab.value);
                  router.push(`${pathname}?tab=${tab.value}`);
                }}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
              </TabsTrigger>
            );
          })}
        </TabsList>
        <TabsContent>
          <ActiveTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
