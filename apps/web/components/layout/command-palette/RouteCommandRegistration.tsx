"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import {
  useRegisterCommands,
  type RegisteredCommand,
} from "@/components/layout/command-palette/CommandRegistry";
import { useCommandPalette } from "@/components/layout/command-palette/CommandPaletteProvider";
import { useAuthStore } from "@/store/auth-store";

type CommandTranslator = (key: string) => string;

interface RouteCommandTemplate {
  id: string;
  labelKey: string;
  categoryKey: string;
  href?: string;
  shortcut?: string;
  keywords?: string[];
}

interface RouteCommandGroup {
  prefixes: string[];
  commands: RouteCommandTemplate[];
}

const ROUTE_COMMAND_GROUPS: RouteCommandGroup[] = [
  {
    prefixes: ["/home"],
    commands: [
      {
        id: "route.home.dashboard",
        labelKey: "routes.home.dashboard",
        categoryKey: "categories.home",
        href: "/dashboard",
      },
      {
        id: "route.home.marketplace",
        labelKey: "routes.home.marketplace",
        categoryKey: "categories.home",
        href: "/marketplace",
        keywords: ["agent", "catalog"],
      },
      {
        id: "route.home.new-conversation",
        labelKey: "routes.home.newConversation",
        categoryKey: "categories.home",
        href: "/conversations/new",
        shortcut: "Shift+N",
      },
    ],
  },
  {
    prefixes: ["/dashboard"],
    commands: [
      {
        id: "route.dashboard.home",
        labelKey: "routes.dashboard.home",
        categoryKey: "categories.dashboard",
        href: "/home",
      },
      {
        id: "route.dashboard.analytics",
        labelKey: "routes.dashboard.analytics",
        categoryKey: "categories.dashboard",
        href: "/analytics",
      },
    ],
  },
  {
    prefixes: ["/marketplace"],
    commands: [
      {
        id: "route.marketplace.search",
        labelKey: "routes.marketplace.search",
        categoryKey: "categories.marketplace",
        shortcut: "/",
        href: "/marketplace",
        keywords: ["agent", "catalog", "search"],
      },
      {
        id: "route.marketplace.compare",
        labelKey: "routes.marketplace.compare",
        categoryKey: "categories.marketplace",
        href: "/marketplace/compare",
      },
    ],
  },
  {
    prefixes: ["/agents"],
    commands: [
      {
        id: "route.agents.directory",
        labelKey: "routes.agents.directory",
        categoryKey: "categories.agents",
        href: "/agents",
        keywords: ["agent", "directory"],
      },
      {
        id: "route.agents.create",
        labelKey: "routes.agents.create",
        categoryKey: "categories.agents",
        href: "/agents/create",
        shortcut: "Shift+A",
      },
      {
        id: "route.agents.marketplace",
        labelKey: "routes.agents.marketplace",
        categoryKey: "categories.agents",
        href: "/marketplace",
      },
    ],
  },
  {
    prefixes: ["/agent-management"],
    commands: [
      {
        id: "route.agent-management.registry",
        labelKey: "routes.agentManagement.registry",
        categoryKey: "categories.agents",
        href: "/agent-management",
      },
      {
        id: "route.agent-management.wizard",
        labelKey: "routes.agentManagement.wizard",
        categoryKey: "categories.agents",
        href: "/agent-management/wizard",
      },
      {
        id: "route.agent-management.contracts",
        labelKey: "routes.agentManagement.contracts",
        categoryKey: "categories.agents",
        href: "/agent-management/contracts/library",
      },
    ],
  },
  {
    prefixes: ["/conversations"],
    commands: [
      {
        id: "route.conversations.new",
        labelKey: "routes.conversations.new",
        categoryKey: "categories.conversations",
        href: "/conversations/new",
        shortcut: "Shift+N",
      },
      {
        id: "route.conversations.list",
        labelKey: "routes.conversations.list",
        categoryKey: "categories.conversations",
        href: "/conversations",
      },
    ],
  },
  {
    prefixes: ["/analytics"],
    commands: [
      {
        id: "route.analytics.open",
        labelKey: "routes.analytics.open",
        categoryKey: "categories.analytics",
        href: "/analytics",
      },
      {
        id: "route.analytics.costs",
        labelKey: "routes.analytics.costs",
        categoryKey: "categories.analytics",
        href: "/costs",
      },
    ],
  },
  {
    prefixes: ["/costs"],
    commands: [
      {
        id: "route.costs.overview",
        labelKey: "routes.costs.overview",
        categoryKey: "categories.costs",
        href: "/costs",
      },
      {
        id: "route.costs.budgets",
        labelKey: "routes.costs.budgets",
        categoryKey: "categories.costs",
        href: "/costs/budgets",
      },
      {
        id: "route.costs.reports",
        labelKey: "routes.costs.reports",
        categoryKey: "categories.costs",
        href: "/costs/reports",
      },
    ],
  },
  {
    prefixes: ["/evaluation-testing"],
    commands: [
      {
        id: "route.evaluation.suites",
        labelKey: "routes.evaluation.suites",
        categoryKey: "categories.evaluation",
        href: "/evaluation-testing",
      },
      {
        id: "route.evaluation.new",
        labelKey: "routes.evaluation.new",
        categoryKey: "categories.evaluation",
        href: "/evaluation-testing/new",
      },
      {
        id: "route.evaluation.simulations",
        labelKey: "routes.evaluation.simulations",
        categoryKey: "categories.evaluation",
        href: "/evaluation-testing/simulations",
      },
    ],
  },
  {
    prefixes: ["/fleet"],
    commands: [
      {
        id: "route.fleet.overview",
        labelKey: "routes.fleet.overview",
        categoryKey: "categories.fleet",
        href: "/fleet",
      },
      {
        id: "route.fleet.operator",
        labelKey: "routes.fleet.operator",
        categoryKey: "categories.fleet",
        href: "/operator",
      },
    ],
  },
  {
    prefixes: ["/operator"],
    commands: [
      {
        id: "route.operator.incidents",
        labelKey: "routes.operator.incidents",
        categoryKey: "categories.operator",
        href: "/operator/incidents",
        keywords: ["alerts", "oncall"],
      },
      {
        id: "route.operator.runbooks",
        labelKey: "routes.operator.runbooks",
        categoryKey: "categories.operator",
        href: "/operator/runbooks",
      },
      {
        id: "route.operator.executions",
        labelKey: "routes.operator.executions",
        categoryKey: "categories.operator",
        href: "/operator",
        keywords: ["execution", "runtime"],
      },
    ],
  },
  {
    prefixes: ["/policies"],
    commands: [
      {
        id: "route.policies.open",
        labelKey: "routes.policies.open",
        categoryKey: "categories.policies",
        href: "/policies",
      },
      {
        id: "route.policies.governance",
        labelKey: "routes.policies.governance",
        categoryKey: "categories.policies",
        href: "/settings/governance",
      },
    ],
  },
  {
    prefixes: ["/trust"],
    commands: [
      {
        id: "route.trust.overview",
        labelKey: "routes.trust.overview",
        categoryKey: "categories.trust",
        href: "/trust",
      },
      {
        id: "route.trust.workbench",
        labelKey: "routes.trust.workbench",
        categoryKey: "categories.trust",
        href: "/trust-workbench",
      },
    ],
  },
  {
    prefixes: ["/trust-workbench"],
    commands: [
      {
        id: "route.trust-workbench.queue",
        labelKey: "routes.trustWorkbench.queue",
        categoryKey: "categories.trust",
        href: "/trust-workbench",
      },
      {
        id: "route.trust-workbench.overview",
        labelKey: "routes.trustWorkbench.overview",
        categoryKey: "categories.trust",
        href: "/trust",
      },
    ],
  },
  {
    prefixes: ["/workflow-editor-monitor"],
    commands: [
      {
        id: "route.workflows.new",
        labelKey: "routes.workflows.new",
        categoryKey: "categories.workflows",
        href: "/workflow-editor-monitor/new",
      },
      {
        id: "route.workflows.monitor",
        labelKey: "routes.workflows.monitor",
        categoryKey: "categories.workflows",
        href: "/workflow-editor-monitor",
      },
      {
        id: "route.workflows.library",
        labelKey: "routes.workflows.library",
        categoryKey: "categories.workflows",
        href: "/workflows",
      },
    ],
  },
  {
    prefixes: ["/workflows"],
    commands: [
      {
        id: "route.workflows.library",
        labelKey: "routes.workflows.library",
        categoryKey: "categories.workflows",
        href: "/workflows",
      },
      {
        id: "route.workflows.new",
        labelKey: "routes.workflows.new",
        categoryKey: "categories.workflows",
        href: "/workflow-editor-monitor/new",
      },
    ],
  },
  {
    prefixes: ["/settings", "/profile"],
    commands: [
      {
        id: "route.settings.preferences",
        labelKey: "routes.settings.preferences",
        categoryKey: "categories.preferences",
        href: "/settings/preferences",
      },
      {
        id: "route.settings.alerts",
        labelKey: "routes.settings.alerts",
        categoryKey: "categories.preferences",
        href: "/settings/alerts",
      },
      {
        id: "route.settings.governance",
        labelKey: "routes.settings.governance",
        categoryKey: "categories.preferences",
        href: "/settings/governance",
      },
      {
        id: "route.settings.visibility",
        labelKey: "routes.settings.visibility",
        categoryKey: "categories.preferences",
        href: "/settings/visibility",
      },
      {
        id: "route.settings.connections",
        labelKey: "routes.settings.connections",
        categoryKey: "categories.preferences",
        href: "/settings/account/connections",
      },
    ],
  },
  {
    prefixes: ["/admin"],
    commands: [
      {
        id: "route.admin.locales",
        labelKey: "routes.admin.locales",
        categoryKey: "categories.admin",
        href: "/admin/locales",
      },
      {
        id: "route.admin.settings",
        labelKey: "routes.admin.settings",
        categoryKey: "categories.admin",
        href: "/admin/settings",
      },
      {
        id: "route.admin.incident-integrations",
        labelKey: "routes.admin.incidentIntegrations",
        categoryKey: "categories.admin",
        href: "/admin/integrations/incidents",
      },
    ],
  },
];

function pathMatchesPrefix(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

function routeCategory(pathname: string, t: CommandTranslator): RegisteredCommand[] {
  return ROUTE_COMMAND_GROUPS.filter((group) =>
    group.prefixes.some((prefix) => pathMatchesPrefix(pathname, prefix)),
  ).flatMap((group) =>
    group.commands.map((command) => ({
      id: command.id,
      label: t(command.labelKey),
      category: t(command.categoryKey),
      ...(command.href ? { href: command.href } : {}),
      ...(command.shortcut ? { shortcut: command.shortcut } : {}),
      ...(command.keywords ? { keywords: command.keywords } : {}),
    })),
  );
}

export function RouteCommandRegistration() {
  const t = useTranslations("commands");
  const pathname = usePathname();
  const router = useRouter();
  const { setTheme, resolvedTheme } = useTheme();
  const { setOpen, openHelp } = useCommandPalette();
  const clearAuth = useAuthStore((state) => state.clearAuth);

  const commands = useMemo<RegisteredCommand[]>(() => {
    const platformCommands: RegisteredCommand[] = [
      {
        id: "platform.toggle-theme",
        label: t("toggleTheme"),
        category: t("categories.platform"),
        shortcut: "Shift+T",
        keywords: ["dark", "light", "contrast"],
        action: () => setTheme(resolvedTheme === "dark" ? "light" : "dark"),
      },
      {
        id: "platform.switch-language",
        label: t("switchLanguage"),
        category: t("categories.platform"),
        shortcut: "Shift+L",
        href: "/settings/preferences#language",
        keywords: ["locale", "i18n"],
      },
      {
        id: "platform.search-marketplace",
        label: t("searchMarketplace"),
        category: t("categories.platform"),
        shortcut: "Shift+M",
        href: "/marketplace",
        keywords: ["agent", "catalog"],
      },
      {
        id: "platform.new-conversation",
        label: t("newConversation"),
        category: t("categories.platform"),
        shortcut: "Shift+N",
        href: "/conversations/new",
        keywords: ["chat", "agent"],
      },
      {
        id: "platform.open-preferences",
        label: t("openPreferences"),
        category: t("categories.platform"),
        shortcut: "Shift+,",
        href: "/settings/preferences",
      },
      {
        id: "platform.sign-out",
        label: t("signOut"),
        category: t("categories.platform"),
        action: () => {
          clearAuth();
          window.location.assign("/login");
        },
      },
      {
        id: "platform.open-help",
        label: t("openHelp"),
        category: t("categories.platform"),
        shortcut: "?",
        action: openHelp,
      },
    ];

    return [...platformCommands, ...routeCategory(pathname, t)];
  }, [clearAuth, openHelp, pathname, resolvedTheme, setTheme, t]);

  useRegisterCommands(
    commands.map((command) =>
      command.href && !command.action
        ? {
            ...command,
            action: () => {
              router.push(command.href ?? "/");
              setOpen(false);
            },
          }
        : command,
    ),
  );

  return null;
}
