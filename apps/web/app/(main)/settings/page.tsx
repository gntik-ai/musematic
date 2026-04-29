import Link from "next/link";
import { Bell, Eye, Landmark, Settings2, UserCog } from "lucide-react";

const settingsSections = [
  {
    href: "/settings/preferences",
    label: "Preferences",
    description: "Theme, language, time zone, notifications, and export format.",
    icon: UserCog,
  },
  {
    href: "/settings/governance",
    label: "Governance",
    description: "Policy and approval controls for this workspace.",
    icon: Landmark,
  },
  {
    href: "/settings/visibility",
    label: "Visibility",
    description: "Zero-trust grants and workspace visibility rules.",
    icon: Eye,
  },
  {
    href: "/settings/alerts",
    label: "Alerts",
    description: "Notification channels and alert routing.",
    icon: Bell,
  },
] as const;

export default function SettingsPage() {
  return (
    <div className="mx-auto w-full max-w-5xl space-y-5">
      <div className="flex items-center gap-3">
        <Settings2 className="h-6 w-6 text-brand-accent" />
        <div>
          <h1 className="text-2xl font-semibold">Settings</h1>
          <p className="text-sm text-muted-foreground">Workspace and account settings.</p>
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {settingsSections.map((section) => {
          const Icon = section.icon;
          return (
            <Link
              key={section.href}
              className="rounded-lg border border-border bg-card p-4 text-card-foreground transition-colors hover:bg-accent"
              href={section.href}
            >
              <div className="flex items-start gap-3">
                <Icon className="mt-1 h-5 w-5 text-brand-accent" />
                <span>
                  <span className="block font-semibold">{section.label}</span>
                  <span className="mt-1 block text-sm text-muted-foreground">{section.description}</span>
                </span>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
