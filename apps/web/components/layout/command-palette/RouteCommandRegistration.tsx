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

function routeCategory(pathname: string, t: CommandTranslator): RegisteredCommand[] {
  const routeCommands: Array<{
    prefix: string;
    category: string;
    commands: RegisteredCommand[];
  }> = [
    {
      prefix: "/marketplace",
      category: t("categories.marketplace"),
      commands: [
        {
          id: "route.marketplace.search",
          label: t("routes.marketplace.search"),
          category: t("categories.marketplace"),
          shortcut: "/",
          href: "/marketplace",
          keywords: ["agent", "catalog", "search"],
        },
        {
          id: "route.marketplace.compare",
          label: t("routes.marketplace.compare"),
          category: t("categories.marketplace"),
          href: "/marketplace/compare",
        },
      ],
    },
    {
      prefix: "/operator",
      category: t("categories.operator"),
      commands: [
        {
          id: "route.operator.incidents",
          label: t("routes.operator.incidents"),
          category: t("categories.operator"),
          href: "/operator/incidents",
          keywords: ["alerts", "oncall"],
        },
        {
          id: "route.operator.runbooks",
          label: t("routes.operator.runbooks"),
          category: t("categories.operator"),
          href: "/operator/runbooks",
        },
      ],
    },
    {
      prefix: "/workflow-editor-monitor",
      category: t("categories.workflows"),
      commands: [
        {
          id: "route.workflows.new",
          label: t("routes.workflows.new"),
          category: t("categories.workflows"),
          href: "/workflow-editor-monitor/new",
        },
        {
          id: "route.workflows.monitor",
          label: t("routes.workflows.monitor"),
          category: t("categories.workflows"),
          href: "/workflow-editor-monitor",
        },
      ],
    },
    {
      prefix: "/settings",
      category: t("categories.preferences"),
      commands: [
        {
          id: "route.settings.preferences",
          label: t("routes.settings.preferences"),
          category: t("categories.preferences"),
          href: "/settings/preferences",
        },
        {
          id: "route.settings.alerts",
          label: t("routes.settings.alerts"),
          category: t("categories.preferences"),
          href: "/settings/alerts",
        },
      ],
    },
    {
      prefix: "/admin",
      category: t("categories.admin"),
      commands: [
        {
          id: "route.admin.locales",
          label: t("routes.admin.locales"),
          category: t("categories.admin"),
          href: "/admin/locales",
        },
        {
          id: "route.admin.settings",
          label: t("routes.admin.settings"),
          category: t("categories.admin"),
          href: "/admin/settings",
        },
      ],
    },
  ];

  return routeCommands.find((group) => pathname.startsWith(group.prefix))?.commands ?? [];
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
