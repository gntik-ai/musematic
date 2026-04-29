"use client";

import { LogOut, Settings, UserRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { LocaleSwitcher } from "@/components/layout/locale-switcher/LocaleSwitcher";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { getInitials } from "@/lib/utils";
import { useAuthStore } from "@/store/auth-store";

export function UserMenu() {
  const user = useAuthStore((state) => state.user);
  const clearAuth = useAuthStore((state) => state.clearAuth);
  const router = useRouter();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" type="button">
          <Avatar>
            {user?.avatarUrl ? <AvatarImage alt={user.displayName} src={user.avatarUrl} /> : null}
            <AvatarFallback>{getInitials(user?.displayName ?? "MU")}</AvatarFallback>
          </Avatar>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="space-y-1">
          <p className="text-sm font-semibold">{user?.displayName ?? "Unknown user"}</p>
          <p className="text-xs font-normal text-muted-foreground">{user?.email ?? "No email"}</p>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onClick={() => {
            router.push("/profile");
          }}
        >
          <UserRound className="h-4 w-4" />
          Profile
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => {
            router.push("/settings/preferences");
          }}
        >
          <Settings className="h-4 w-4" />
          Preferences
        </DropdownMenuItem>
        <LocaleSwitcher />
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onClick={() => {
            clearAuth();
            window.location.assign("/login");
          }}
        >
          <LogOut className="h-4 w-4" />
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
