# REST API Contracts: Workspaces Bounded Context

**Feature**: 018-workspaces-bounded-context  
**Date**: 2026-04-11  
**Base path**: `/api/v1/workspaces`

All endpoints require authentication (JWT). Workspace-scoped endpoints require workspace membership with the minimum role indicated.

---

## Workspace CRUD

### POST /api/v1/workspaces
**Create a workspace**  
Auth: Authenticated user  
Enforces: workspace limit check

| Field | Request Body |
|-------|-------------|
| name | string, required, 1–100 chars |
| description | string, optional, max 500 chars |

**201 Created** → `WorkspaceResponse` (user is auto-added as owner)  
**409 Conflict** → workspace name already exists for this user  
**403 Forbidden** → workspace limit reached

---

### GET /api/v1/workspaces
**List workspaces for current user**  
Auth: Authenticated user  
Query: `page` (default 1), `page_size` (default 20), `status` (optional filter: active, archived)

**200 OK** → `WorkspaceListResponse`

---

### GET /api/v1/workspaces/{workspace_id}
**Get workspace by ID**  
Auth: Workspace member (any role)

**200 OK** → `WorkspaceResponse`  
**404 Not Found** → workspace does not exist or user is not a member

---

### PATCH /api/v1/workspaces/{workspace_id}
**Update workspace name/description**  
Auth: Workspace admin or owner

| Field | Request Body |
|-------|-------------|
| name | string, optional, 1–100 chars |
| description | string, optional, max 500 chars |

**200 OK** → `WorkspaceResponse`  
**409 Conflict** → new name already exists for this owner

---

### POST /api/v1/workspaces/{workspace_id}/archive
**Archive workspace (soft delete)**  
Auth: Workspace owner

**200 OK** → `WorkspaceResponse` (status: archived)  
**409 Conflict** → workspace already archived

---

### POST /api/v1/workspaces/{workspace_id}/restore
**Restore archived workspace**  
Auth: Workspace owner

**200 OK** → `WorkspaceResponse` (status: active)  
**409 Conflict** → workspace is not archived

---

### DELETE /api/v1/workspaces/{workspace_id}
**Permanently delete workspace (deferred cleanup)**  
Auth: Platform admin or workspace owner

**202 Accepted** → deletion scheduled  
**409 Conflict** → workspace must be archived first

---

## Membership Management

### POST /api/v1/workspaces/{workspace_id}/members
**Add a member to the workspace**  
Auth: Workspace admin or owner

| Field | Request Body |
|-------|-------------|
| user_id | UUID, required |
| role | WorkspaceRole, required (member, viewer, admin) |

**201 Created** → `MembershipResponse`  
**409 Conflict** → user is already a member  
**422 Unprocessable** → cannot add member as owner (owner is set at creation)

---

### GET /api/v1/workspaces/{workspace_id}/members
**List workspace members**  
Auth: Workspace member (any role)  
Query: `page` (default 1), `page_size` (default 50)

**200 OK** → `MemberListResponse` (sorted by role rank, then display name)

---

### PATCH /api/v1/workspaces/{workspace_id}/members/{user_id}
**Change a member's role**  
Auth: Workspace admin or owner

| Field | Request Body |
|-------|-------------|
| role | WorkspaceRole, required |

**200 OK** → `MembershipResponse`  
**403 Forbidden** → admin cannot promote to owner or demote an owner  
**404 Not Found** → user is not a member of this workspace

---

### DELETE /api/v1/workspaces/{workspace_id}/members/{user_id}
**Remove a member from the workspace**  
Auth: Workspace admin or owner (owner cannot remove themselves if they are the last owner)

**204 No Content**  
**409 Conflict** → cannot remove the last owner

---

## Workspace Goals

### POST /api/v1/workspaces/{workspace_id}/goals
**Create a goal**  
Auth: Workspace member (member role or above)

| Field | Request Body |
|-------|-------------|
| title | string, required, 1–200 chars |
| description | string, optional, max 2000 chars |

**201 Created** → `GoalResponse` (GID auto-generated, status: open)

---

### GET /api/v1/workspaces/{workspace_id}/goals
**List goals for the workspace**  
Auth: Workspace member (any role)  
Query: `status` (optional filter), `page` (default 1), `page_size` (default 20)

**200 OK** → `GoalListResponse`

---

### GET /api/v1/workspaces/{workspace_id}/goals/{goal_id}
**Get a single goal by ID**  
Auth: Workspace member (any role)

**200 OK** → `GoalResponse`  
**404 Not Found**

---

### PATCH /api/v1/workspaces/{workspace_id}/goals/{goal_id}
**Update goal status**  
Auth: Workspace member (member role or above)

| Field | Request Body |
|-------|-------------|
| status | GoalStatus, required |

**200 OK** → `GoalResponse`  
**409 Conflict** → invalid status transition (e.g., completed → in_progress)

---

## Visibility Grants

### PUT /api/v1/workspaces/{workspace_id}/visibility
**Set or replace workspace visibility grants**  
Auth: Workspace admin or owner

| Field | Request Body |
|-------|-------------|
| visibility_agents | list[string], required — FQN patterns |
| visibility_tools | list[string], required — FQN patterns |

**200 OK** → `VisibilityGrantResponse`

---

### GET /api/v1/workspaces/{workspace_id}/visibility
**Get workspace visibility grants**  
Auth: Workspace member (any role)

**200 OK** → `VisibilityGrantResponse`  
**404 Not Found** → no visibility grant set (workspace uses zero-trust default only)

---

### DELETE /api/v1/workspaces/{workspace_id}/visibility
**Remove workspace visibility grants (return to zero-trust default)**  
Auth: Workspace admin or owner

**204 No Content**

---

## Workspace Settings

### GET /api/v1/workspaces/{workspace_id}/settings
**Get workspace settings (super-context subscriptions)**  
Auth: Workspace member (any role)

**200 OK** → `SettingsResponse`

---

### PATCH /api/v1/workspaces/{workspace_id}/settings
**Update workspace settings**  
Auth: Workspace admin or owner

| Field | Request Body |
|-------|-------------|
| subscribed_agents | list[string], optional — FQN patterns |
| subscribed_fleets | list[UUID], optional |
| subscribed_policies | list[UUID], optional |
| subscribed_connectors | list[UUID], optional |

**200 OK** → `SettingsResponse`

---

## Internal Service Interface (In-Process)

These are not REST endpoints. They are called by other bounded contexts via in-process function calls.

### `workspaces_service.get_workspace_visibility_grant(workspace_id: UUID) → VisibilityGrant | None`
Called by: registry bounded context (agent discovery)  
Returns visibility grant for the workspace or None if not set.

### `workspaces_service.get_user_workspace_ids(user_id: UUID) → list[UUID]`
Called by: auth middleware (to populate workspace context in JWT claims)  
Returns all workspace IDs where the user is an active member.

---

## Summary

| Category | Count |
|----------|-------|
| Workspace CRUD | 7 endpoints |
| Membership | 4 endpoints |
| Goals | 4 endpoints |
| Visibility | 3 endpoints |
| Settings | 2 endpoints |
| **Total** | **20 endpoints** |
| Internal interfaces | 2 service methods |
