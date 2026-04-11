export type RoleType =
  | "superadmin"
  | "platform_admin"
  | "workspace_owner"
  | "workspace_admin"
  | "workspace_editor"
  | "workspace_viewer"
  | "agent_operator"
  | "agent_viewer"
  | "trust_officer"
  | "policy_manager"
  | "analytics_viewer"
  | "creator"
  | "operator"
  | "viewer"
  | "auditor"
  | "agent"
  | "service_account";

export interface UserProfile {
  id: string;
  email: string;
  displayName: string;
  avatarUrl: string | null;
  roles: RoleType[];
  workspaceId: string | null;
  mfaEnrolled: boolean;
}

export interface AuthState {
  user: UserProfile | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

export interface TokenPair {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
}

export interface AuthSession extends TokenPair {
  user: UserProfile;
}
