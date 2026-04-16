# API Contracts Consumed: Agent Catalog and Creator Workbench

Documents the backend API endpoints this frontend feature consumes.  
All requests require `Authorization: Bearer <access_token>`.  
Base URL prefix: `/api/v1`

---

## Registry API (feature 021)

### Agent List
```
GET /api/v1/registry/agents
  ?workspace_id={id}&namespace={ns}&status={status}&maturity={level}&search={term}&limit={n}&cursor={cursor}&sort_by={field}&sort_order={asc|desc}
→ { items: AgentCatalogEntry[], next_cursor: string | null, total: number }
```

### Agent Detail
```
GET /api/v1/registry/agents/{fqn}
→ AgentDetail
Errors: 404 if agent not found or not visible
```

### Create Agent (from upload)
```
POST /api/v1/registry/agents/upload
Content-Type: multipart/form-data
body: { package: File, workspace_id: string }
→ { agent_fqn: string, status: "draft", validation_errors: string[] }  (201 or 422 with errors)
Progress via XHR upload progress events
```

### Update Agent Metadata
```
PUT /api/v1/registry/agents/{fqn}/metadata
If-Unmodified-Since: {last_modified_timestamp}
body: MetadataUpdateRequest
→ AgentDetail  (200)
Errors: 412 if stale (concurrent edit conflict)
```

### Validate Agent for Publication
```
POST /api/v1/registry/agents/{fqn}/validate
→ ValidationResult
```

### Publish Agent
```
POST /api/v1/registry/agents/{fqn}/publish
→ PublicationSummary  (200)
Errors: 409 if validation not passed
```

### List Agent Namespaces (for namespace selector)
```
GET /api/v1/registry/namespaces
  ?workspace_id={id}
→ { items: [{ namespace: string, agent_count: number }] }
```

---

## Agent Revisions API (feature 021)

### List Revisions
```
GET /api/v1/registry/agents/{fqn}/revisions
  ?workspace_id={id}&limit={n}&cursor={cursor}
→ { items: AgentRevision[], next_cursor: string | null }
```

### Get Revision Diff
```
GET /api/v1/registry/agents/{fqn}/revisions/{revision_a}/diff/{revision_b}
→ RevisionDiff
```

### Rollback to Revision
```
POST /api/v1/registry/agents/{fqn}/revisions/{revision_number}/rollback
→ AgentRevision  (201 — new revision created)
Errors: 409 if deprecated references found
```

---

## Health Score API (feature 021 / 034)

### Get Agent Health Score
```
GET /api/v1/registry/agents/{fqn}/health
→ AgentHealthScore
```

---

## Policy API (feature 028)

### List Agent Policies
```
GET /api/v1/policies
  ?agent_fqn={fqn}&workspace_id={id}
→ { items: [{ policy_id, name, type, enforcement_status }] }
```

---

## Composition API (feature 038)

### Generate Blueprint from Description
```
POST /api/v1/composition/agent-blueprint
body: { description: string, workspace_id: string }
→ CompositionBlueprint  (201)
Errors: 503 if composition service unavailable
```

### Get Composition Blueprint
```
GET /api/v1/composition/agent-blueprint/{blueprint_id}
→ CompositionBlueprint
```

### Create Agent from Blueprint
```
POST /api/v1/registry/agents
body: { blueprint_id: string, workspace_id: string, metadata: MetadataFormValues }
→ AgentDetail  (201)
```

---

## TanStack Query Hook Map

| Hook | Endpoint | Type |
|------|----------|------|
| `useAgents(filters)` | GET /registry/agents | `useInfiniteQuery` |
| `useAgent(fqn)` | GET /registry/agents/{fqn} | `useQuery` |
| `useAgentHealth(fqn)` | GET /registry/agents/{fqn}/health | `useQuery` |
| `useAgentRevisions(fqn)` | GET /registry/agents/{fqn}/revisions | `useQuery` |
| `useRevisionDiff(fqn, a, b)` | GET /registry/agents/{fqn}/revisions/{a}/diff/{b} | `useQuery` |
| `useAgentPolicies(fqn)` | GET /policies?agent_fqn={fqn} | `useQuery` |
| `useNamespaces()` | GET /registry/namespaces | `useQuery` |
| `useUpdateAgentMetadata()` | PUT /registry/agents/{fqn}/metadata | `useMutation` |
| `useValidateAgent()` | POST /registry/agents/{fqn}/validate | `useMutation` |
| `usePublishAgent()` | POST /registry/agents/{fqn}/publish | `useMutation` |
| `useRollbackRevision()` | POST /registry/agents/{fqn}/revisions/{n}/rollback | `useMutation` |
| `useUploadAgentPackage()` | POST /registry/agents/upload | `useMutation` (XHR) |
| `useGenerateBlueprint()` | POST /composition/agent-blueprint | `useMutation` |
| `useCreateFromBlueprint()` | POST /registry/agents | `useMutation` |
