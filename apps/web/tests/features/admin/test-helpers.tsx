import { useAuthStore } from "@/store/auth-store";

export function setPlatformAdminUser() {
  useAuthStore.setState({
    accessToken: "access-token",
    isAuthenticated: true,
    refreshToken: "refresh-token",
    user: {
      id: "admin-1",
      email: "pat.admin@musematic.dev",
      displayName: "Pat Admin",
      avatarUrl: null,
      mfaEnrolled: true,
      roles: ["platform_admin"],
      workspaceId: "workspace-1",
    },
  } as never);
}

export function setNonAdminUser() {
  useAuthStore.setState({
    accessToken: "access-token",
    isAuthenticated: true,
    refreshToken: "refresh-token",
    user: {
      id: "owner-1",
      email: "owner@musematic.dev",
      displayName: "Workspace Owner",
      avatarUrl: null,
      mfaEnrolled: true,
      roles: ["workspace_owner"],
      workspaceId: "workspace-1",
    },
  } as never);
}
