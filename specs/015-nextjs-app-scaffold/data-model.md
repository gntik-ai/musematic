# Data Model: Next.js Application Scaffold

**Feature**: 015-nextjs-app-scaffold  
**Date**: 2026-04-11  
**Phase**: 1 — Design

---

## TypeScript Type Definitions

### `types/auth.ts`

```typescript
export type RoleType =
  | 'superadmin'
  | 'workspace_admin'
  | 'workspace_editor'
  | 'workspace_viewer'
  | 'agent_operator'
  | 'agent_viewer'
  | 'trust_officer'
  | 'policy_manager'
  | 'analytics_viewer'
  | 'service_account';

export interface UserProfile {
  id: string;                   // UUID
  email: string;
  displayName: string;
  avatarUrl: string | null;
  roles: RoleType[];
  workspaceId: string | null;   // Active workspace (may be null until selected)
}

export interface AuthState {
  user: UserProfile | null;
  accessToken: string | null;
  refreshToken: string | null;   // Persisted to localStorage via Zustand persist
  isAuthenticated: boolean;
  isLoading: boolean;
}

export interface TokenPair {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;             // Seconds until access token expiry
}
```

### `types/workspace.ts`

```typescript
export interface Workspace {
  id: string;                    // UUID
  name: string;
  slug: string;
  description: string | null;
  memberCount: number;
  createdAt: string;             // ISO 8601
}

export interface WorkspaceState {
  currentWorkspace: Workspace | null;
  workspaceList: Workspace[];
  sidebarCollapsed: boolean;     // Persisted to localStorage
  isLoading: boolean;
}
```

### `types/api.ts`

```typescript
export interface ApiErrorDetail {
  field?: string;
  message: string;
}

export interface ApiErrorPayload {
  code: string;
  message: string;
  details?: ApiErrorDetail[];
}

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number,
    public readonly details?: ApiErrorDetail[]
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  hasNext: boolean;
  hasPrev: boolean;
}

export interface CursorPaginatedResponse<T> {
  items: T[];
  nextCursor: string | null;
  prevCursor: string | null;
  total: number;
}

// Internal fetch client request options
export interface ApiRequestOptions extends RequestInit {
  skipAuth?: boolean;            // Skip JWT injection (e.g., login endpoint)
  skipRetry?: boolean;           // Skip retry logic for non-idempotent requests
}
```

### `types/navigation.ts`

```typescript
import type { RoleType } from './auth';

export interface NavItem {
  id: string;
  label: string;
  icon: string;                  // Lucide icon name
  href: string;
  requiredRoles: RoleType[];     // Empty array = visible to all authenticated users
  badge?: string | number;       // Optional badge (e.g., notification count)
  children?: NavItem[];          // Nested navigation items
}

export interface BreadcrumbSegment {
  label: string;
  href: string | null;           // null for the current (last) segment
}
```

### `types/websocket.ts`

```typescript
export type WsConnectionState = 'connecting' | 'connected' | 'disconnected' | 'reconnecting';

export interface WsEvent<T = unknown> {
  channel: string;
  type: string;
  payload: T;
  timestamp: string;             // ISO 8601
}

export interface WsMessage {
  channel: string;
  type: string;
  payload: unknown;
}

export type WsEventHandler<T = unknown> = (event: WsEvent<T>) => void;
export type WsUnsubscribeFn = () => void;
```

---

## Zustand Store Shapes

### `store/auth-store.ts`

```typescript
import type { AuthState, UserProfile, TokenPair } from '@/types/auth';

interface AuthActions {
  setTokens: (tokens: TokenPair) => void;
  setUser: (user: UserProfile) => void;
  clearAuth: () => void;
  setLoading: (loading: boolean) => void;
}

// Persisted slice — only refreshToken stored in localStorage
interface AuthPersistedState {
  refreshToken: string | null;
}

// Full store type = AuthState + AuthActions
export type AuthStore = AuthState & AuthActions;
```

**Persistence config**: `zustand/middleware persist` with key `auth-storage`, partialize to `{ refreshToken }` only. Access token and user profile are NOT persisted — re-acquired on page load via the refresh flow.

### `store/workspace-store.ts`

```typescript
import type { WorkspaceState, Workspace } from '@/types/workspace';

interface WorkspaceActions {
  setCurrentWorkspace: (workspace: Workspace) => void;  // Also calls queryClient.invalidateQueries()
  setWorkspaceList: (list: Workspace[]) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setLoading: (loading: boolean) => void;
}

export type WorkspaceStore = WorkspaceState & WorkspaceActions;
```

**Persistence config**: `zustand/middleware persist` with key `workspace-storage`, partialize to `{ currentWorkspace, sidebarCollapsed }`.

---

## Component Prop Interfaces

### Shared components — `components/shared/`

```typescript
// DataTable
import type { ColumnDef, PaginationState, SortingState, ColumnFiltersState } from '@tanstack/react-table';

export interface DataTableProps<TData> {
  columns: ColumnDef<TData>[];
  data: TData[];
  isLoading?: boolean;
  emptyStateMessage?: string;
  emptyStateCta?: React.ReactNode;
  pageSize?: number;                // Default: 20
  enableSorting?: boolean;          // Default: true
  enableFiltering?: boolean;        // Default: true
  onPaginationChange?: (state: PaginationState) => void;
  onSortingChange?: (state: SortingState) => void;
  onFilterChange?: (state: ColumnFiltersState) => void;
  totalCount?: number;              // For server-side pagination
}

// MetricCard
export interface SparklineDataPoint {
  value: number;
  timestamp: string;
}

export type TrendDirection = 'up' | 'down' | 'neutral';

export interface MetricCardProps {
  title: string;
  value: string | number;
  unit?: string;
  trend?: TrendDirection;
  trendValue?: string;              // e.g., "+12%" or "-5 from yesterday"
  sparklineData?: SparklineDataPoint[];
  isLoading?: boolean;
  className?: string;
}

// StatusBadge
export type StatusSemantic = 'healthy' | 'warning' | 'error' | 'inactive' | 'pending' | 'running';

export interface StatusBadgeProps {
  status: StatusSemantic;
  label?: string;                   // Override default label derived from status
  size?: 'sm' | 'md' | 'lg';       // Default: 'md'
  showIcon?: boolean;               // Default: true
}

// ScoreGauge
export interface ScoreGaugeProps {
  score: number;                    // 0–100
  label?: string;
  size?: 'sm' | 'md' | 'lg';       // sm=80px, md=120px, lg=160px
  thresholds?: {
    warning: number;                // Default: 60
    good: number;                   // Default: 80
  };
}

// EmptyState
export interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

// ConfirmDialog
export interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel?: string;            // Default: "Confirm"
  cancelLabel?: string;             // Default: "Cancel"
  variant?: 'default' | 'destructive';  // Default: 'default'
  onConfirm: () => void | Promise<void>;
  isLoading?: boolean;
}

// CodeBlock
export interface CodeBlockProps {
  code: string;
  language?: string;                // Default: 'plaintext'
  showLineNumbers?: boolean;        // Default: false
  showCopyButton?: boolean;         // Default: true
  maxHeight?: number;               // CSS px value for scrollable container
  className?: string;
}

// JsonViewer
export interface JsonViewerProps {
  data: unknown;
  defaultExpanded?: boolean;        // Default: true for root, false for nested
  maxDepth?: number;                // Default: 3
  showCopyButton?: boolean;         // Default: true
  className?: string;
}

// Timeline
export interface TimelineEvent {
  id: string;
  timestamp: string;                // ISO 8601
  label: string;
  description?: string;
  status?: StatusSemantic;
  icon?: React.ReactNode;
}

export interface TimelineProps {
  events: TimelineEvent[];
  isLoading?: boolean;
  emptyStateMessage?: string;
  className?: string;
}

// SearchInput
export interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  debounceMs?: number;              // Default: 300
  isLoading?: boolean;
  className?: string;
}

// FilterBar
export interface FilterOption {
  value: string;
  label: string;
  count?: number;
}

export interface FilterBarFilter {
  key: string;
  label: string;
  options: FilterOption[];
  multiSelect?: boolean;            // Default: false
}

export interface FilterBarProps {
  filters: FilterBarFilter[];
  values: Record<string, string | string[]>;
  onChange: (key: string, value: string | string[]) => void;
  onClear?: () => void;
  className?: string;
}
```

---

## WebSocket Client Interface

```typescript
// lib/ws.ts (interface contract)
export interface IWebSocketClient {
  readonly connectionState: WsConnectionState;
  connect(): void;
  disconnect(): void;
  subscribe<T = unknown>(channel: string, handler: WsEventHandler<T>): WsUnsubscribeFn;
  send(channel: string, type: string, payload: unknown): void;
  onStateChange(handler: (state: WsConnectionState) => void): () => void;
}
```

---

## API Client Interface

```typescript
// lib/api.ts (interface contract)
export interface IApiClient {
  get<T>(path: string, options?: ApiRequestOptions): Promise<T>;
  post<T>(path: string, body?: unknown, options?: ApiRequestOptions): Promise<T>;
  put<T>(path: string, body?: unknown, options?: ApiRequestOptions): Promise<T>;
  patch<T>(path: string, body?: unknown, options?: ApiRequestOptions): Promise<T>;
  delete<T>(path: string, options?: ApiRequestOptions): Promise<T>;
}

export function createApiClient(baseUrl: string): IApiClient;
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_API_URL` | Yes | Backend API base URL |
| `NEXT_PUBLIC_WS_URL` | Yes | WebSocket server URL |
| `NEXT_PUBLIC_APP_ENV` | No | Environment name (development/staging/production) |
