"use client";

import { ChevronDown, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { useWorkspaceStore } from "@/store/workspace-store";

export function WorkspaceSelector() {
  const currentWorkspace = useWorkspaceStore((state) => state.currentWorkspace);
  const workspaceList = useWorkspaceStore((state) => state.workspaceList);
  const setCurrentWorkspace = useWorkspaceStore((state) => state.setCurrentWorkspace);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button className="min-w-52 justify-between" variant="outline">
          <span className="truncate">{currentWorkspace?.name ?? "Select workspace"}</span>
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-64">
        {workspaceList.map((workspace) => (
          <DropdownMenuItem key={workspace.id} onClick={() => setCurrentWorkspace(workspace)}>
            <span className="flex flex-1 flex-col text-left">
              <span className="font-medium">{workspace.name}</span>
              <span className="text-xs text-muted-foreground">{workspace.slug}</span>
            </span>
            {currentWorkspace?.id === workspace.id ? <Check className="h-4 w-4 text-brand-primary" /> : null}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
