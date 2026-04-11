export interface Workspace {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  memberCount: number;
  createdAt: string;
}

export interface WorkspaceState {
  currentWorkspace: Workspace | null;
  workspaceList: Workspace[];
  sidebarCollapsed: boolean;
  isLoading: boolean;
}
