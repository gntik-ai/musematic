"use client";

import Link from "next/link";
import {
  MessageSquarePlus,
  Store,
  Upload,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { useAuthStore } from "@/store/auth-store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { QuickAction } from "@/lib/types/home";

const QUICK_ACTIONS: QuickAction[] = [
  {
    id: "new-conversation",
    label: "New Conversation",
    icon: "MessageSquarePlus",
    href: "/conversations/new",
  },
  {
    id: "upload-agent",
    label: "Upload Agent",
    icon: "Upload",
    href: "/agents/create",
    requiredPermission: "write",
  },
  {
    id: "create-workflow",
    label: "Create Workflow",
    icon: "Workflow",
    href: "/workflows",
    requiredPermission: "write",
  },
  {
    id: "browse-marketplace",
    label: "Browse Marketplace",
    icon: "Store",
    href: "/marketplace",
  },
];

const iconMap: Record<string, LucideIcon> = {
  MessageSquarePlus,
  Upload,
  Workflow,
  Store,
};

const writeRoles = new Set([
  "superadmin",
  "platform_admin",
  "workspace_owner",
  "workspace_admin",
  "workspace_editor",
  "agent_operator",
  "policy_manager",
  "trust_officer",
  "creator",
  "operator",
]);

function hasWriteAccess(roles: string[]): boolean {
  return roles.some((role) => writeRoles.has(role));
}

export function QuickActions() {
  const roles = useAuthStore((state) => state.user?.roles ?? []);
  const canWrite = hasWriteAccess(roles);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Quick actions</CardTitle>
      </CardHeader>
      <CardContent>
        <TooltipProvider>
          <div className="flex flex-wrap gap-3">
            {QUICK_ACTIONS.map((action) => {
              const Icon = iconMap[action.icon] ?? MessageSquarePlus;
              const disabled = action.requiredPermission === "write" && !canWrite;

              if (disabled) {
                return (
                  <Tooltip key={action.id}>
                    <TooltipTrigger>
                      <span
                        className="inline-flex"
                        title="Requires write access"
                      >
                        <Button
                          aria-disabled="true"
                          className="focus-visible:ring-2"
                          disabled
                          variant="outline"
                        >
                          <Icon className="h-4 w-4" />
                          {action.label}
                        </Button>
                      </span>
                    </TooltipTrigger>
                    <TooltipContent>Requires write access</TooltipContent>
                  </Tooltip>
                );
              }

              return (
                <Button
                  key={action.id}
                  asChild
                  className="focus-visible:ring-2"
                  variant="outline"
                >
                  <Link href={action.href}>
                    <Icon className="h-4 w-4" />
                    {action.label}
                  </Link>
                </Button>
              );
            })}
          </div>
        </TooltipProvider>
      </CardContent>
    </Card>
  );
}
