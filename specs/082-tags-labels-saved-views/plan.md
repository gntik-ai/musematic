# Implementation Plan: Tags, Labels, and Saved Views

**Branch**: `082-tags-labels-saved-views` | **Date**: 2026-04-26 | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

## Summary

Stand up the polymorphic tagging/labeling substrate that constitution rule 14 already mandates ("Every new entity supports tags and labels. Add the polymorphic `entity_tags` / `entity_labels` relations when introducing new entity types; never reinvent tagging per context") and that the constitution's REST registry already reserves slots for (`/api/v1/tags/*`, `/api/v1/labels/*`, `/api/v1/saved-views/*` at lines 808–810). The brownfield input nominated `policies/services/policy_engine.py` and `registry/services/registry_query_service.py` as modification targets — **neither file exists**. The actual policy match-condition evaluation lives in `governance/services/judge_service.py:19 JudgeService.process_signal` (`:39`), and registry filtering lives in `registry/service.py:371 RegistryService.list_agents`. The plan extends those real call sites rather than creating misnamed modules. The substrate lives in `common/tagging/` (greenfield — `apps/control-plane/src/platform/common/` does not currently contain a `tagging/` subfolder, and no migration mentions `entity_tags` / `entity_labels` / `saved_views`). Three tables in a single Alembic migration `065_tags_labels_saved_views.py` carry the substrate; cascade-on-entity-delete is enforced by the application's BC delete paths since the polymorphic `(entity_type, entity_id)` shape cannot use a typed FK with `ON DELETE CASCADE` (one of the documented complexity-tracking entries below). The seven major entity types — `workspaces` (`workspaces/models.py:59`), `agents` (`registry/models.py:77 AgentProfile`), `fleets` (`fleets/models.py:50`), `workflows` (`workflows/models.py:42 WorkflowDefinition`), `policies` (`policies/models.py:46 PolicyPolicy`), `certifications` (`trust/models.py:91 TrustCertification`), and `evaluation_runs` (`evaluation/models.py:175 EvaluationRun` — note: the spec/input said "evaluation_suites" but the actual table is `evaluation_runs`; the plan uses the real name and clarifies in `data-model.md`) — each get a small `entity_type` discriminator string assigned in `common/tagging/constants.py` and a small additive integration into their listing endpoint to accept `?tags=` and `?label.key=value` filters. **Label-based policy expressions** are a small DSL: `key=value | key!=value | HAS key | NOT HAS key | … AND … | … OR … | NOT … | (…)` parsed into a typed AST cached at policy load and evaluated in O(label-count) at the gateway hot path. **Saved views** are owned per-user with optional workspace sharing; the orphan-owner case (FR-512.5) resolves to "transfer ownership to the workspace's first active superadmin, with a structured-log notice" rather than silent deletion. **No new bounded context is created** — `common/tagging/` is a shared substrate per the constitutional pattern (`common/` houses cross-cutting concerns like correlation, audit-hook, pagination); creating a `tagging/` BC would split work that is by design polymorphic across BCs.

## Technical Context

**Language/Version**: Python 3.12+ (control plane). No Go changes.
**Primary Dependencies** (already present): FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, Alembic 1.13+, aiokafka 0.11+ (audit-event emission), redis-py 5.x async (compiled-AST cache for label expressions per FR-511.19, SC-009), pyparsing 3.x — **NEW dependency** for the small label-expression DSL parser, OR a hand-rolled recursive-descent parser if the team prefers zero-new-dep (recommended: hand-rolled — the grammar is small enough that a 200-line parser keeps the dep surface clean).
**Storage**: PostgreSQL — 3 new tables (`entity_tags`, `entity_labels`, `saved_views`) via Alembic migration `065_tags_labels_saved_views.py`. Redis — 1 new key family: `tags:label_expression_ast:{policy_id}:{version}` (compiled-AST cache; TTL = `policy_cache_ttl_seconds` from existing policies BC; invalidated on policy save). No MinIO/S3 paths.
**Testing**: pytest + pytest-asyncio 8.x. Existing fixtures for `audit/`, `policies/`, `governance/`, `notifications/`, the seven entity BCs, and the frontend list pages are reused. New fixtures for the label-expression DSL property-based testing harness (`hypothesis` — already in test dependencies for prior features) and a per-entity-type integration harness that exercises the same tag/label/listing flow uniformly across all seven types.
**Target Platform**: Linux server (control plane). No new runtime profile; the substrate runs on the existing `api` profile. No APScheduler jobs are needed for v1 (no background work).
**Project Type**: Web service (FastAPI control plane shared substrate — new `common/tagging/` module + small additive extensions to seven entity BCs + one extension to `governance/services/judge_service.py` + frontend tag/label/saved-view UI integrated into seven existing list pages).
**Performance Goals**: Tag attachment / detachment ≤ 20 ms p95 (single PG insert/delete + audit-chain entry). Cross-entity tag search ≤ 200 ms p95 over millions of tag rows (covered by the index on `(tag)` from migration `065`). Label-filtered entity listings ≤ 100 ms additional p95 over the un-filtered listing (a single JOIN against `entity_labels` with the index on `(label_key, label_value)`). **Policy gateway p95 latency MUST NOT regress** (FR-511.19, SC-009) — compiled label-expression ASTs cached in Redis under `tags:label_expression_ast:*` and resolved via in-process LRU on top so steady-state evaluation hits zero database calls per gateway evaluation; the labels themselves are loaded into the existing per-evaluation `target` context that the gateway already passes around. Saved-view list query ≤ 50 ms p95 (small table, scoped to user + workspace).
**Constraints**: Polymorphic `(entity_type, entity_id)` composite cannot use a typed PG `FOREIGN KEY ... ON DELETE CASCADE` directly (the entity_id can reference any of seven different tables). Cascade enforcement therefore lives in **each entity BC's delete path**: `WorkspaceService.delete`, `RegistryService.delete_agent`, etc., each call `TagService.cascade_on_entity_deletion(entity_type, entity_id)` and `LabelService.cascade_on_entity_deletion(...)` inside the same SQLAlchemy transaction so the deletion + tag/label cascade are atomic. This is documented in `data-model.md` and verified by SC-003. Reserved label-key namespaces (`system.*`, `platform.*`) are enforced server-side at the `LabelService.attach` boundary; non-superadmin / non-service-account writes to reserved namespaces raise 403 (FR-511.13). Tag normalisation is documented as **case-sensitive, whitespace-trimmed, max 128 chars, ASCII-printable + hyphen + underscore + period** (decided here so the spec's edge case "Tag normalisation" lands deterministically; recorded in `research.md`). Label values are strings only at v1 (spec § Out of Scope). Cross-entity tag search filters at the SQL layer (NOT the response serializer) per FR-CC-1.
**Scale/Scope**: ~1,000 entities × ~10 tags/labels each at steady state for a typical deployment = ~10,000 rows per table. Hot tags (`production`, `customer-facing`, etc.) may concentrate on hundreds of entities — the index on `(tag)` is the read path for cross-entity search and remains performant well past 1M rows. Label expressions in policies: ~10–50 policies per deployment carry expressions; cached AST size is bounded.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Source | Status | Notes |
|---|---|---|---|
| Brownfield rule 1 — never rewrite | Constitution § Brownfield | ✅ Pass | New `common/tagging/` module. Modifies seven entity BC routers/services additively (each gains a small filter-parameter handler that delegates to `TagService.filter_query` / `LabelService.filter_query`); modifies `governance/services/judge_service.py:19` additively (adds the label-expression evaluator into the existing match-condition flow); no file rewritten. |
| Brownfield rule 2 — Alembic only | Constitution § Brownfield | ✅ Pass | Single migration `065_tags_labels_saved_views.py` adds 3 tables. No raw DDL. |
| Brownfield rule 3 — preserve tests | Constitution § Brownfield | ✅ Pass | Listing-endpoint extensions are query-parameter-additive: existing callers omit the new params and see no behaviour change. Each entity's existing list test stays green. |
| Brownfield rule 4 — use existing patterns | Constitution § Brownfield | ✅ Pass | New module follows the `common/` convention (service-per-concern; e.g., `common/correlation.py`, `common/pagination.py`). REST surfaces under the constitutionally-declared prefixes use the same router-mount pattern as other BCs (`main.py:1540–1579`). Audit-chain emission goes through `AuditChainService.append` (`audit/service.py:49`). The label-expression parser follows the structural-validation pattern from prior policies-engine extensions. |
| Brownfield rule 5 — cite exact files | Constitution § Brownfield | ✅ Pass | Project Structure below names every file; integration seams cite file:line for all call sites. |
| Brownfield rule 6 — additive enums | Constitution § Brownfield | ✅ Pass | New string-CHECK constants (`ENTITY_TYPES = ("workspace","agent","fleet","workflow","policy","certification","evaluation_run")`) live in `common/tagging/constants.py`. No mutation of existing enums. |
| Brownfield rule 7 — backwards-compatible APIs | Constitution § Brownfield | ✅ Pass | Listing endpoints accept the new tag/label filter parameters as optional query params; omitted params give existing behaviour. New endpoints under `/api/v1/tags/*`, `/api/v1/labels/*`, `/api/v1/saved-views/*` are additive. Policy authoring with no label expression continues to work; expressions are an opt-in match condition. |
| Brownfield rule 8 — feature flags | Constitution § Brownfield | ✅ Pass | The substrate is foundational (rule 14 mandate) and is not gated. The label-expression evaluator path is gated by per-policy presence of an expression — a policy with no expression carries no evaluation cost. |
| Rule 9 — every PII operation audited | Constitution § Domain | ✅ Pass | Every tag, label, and saved-view mutation emits an audit-chain entry via `AuditChainService.append` (FR-CC-2, SC-013). Saved-view filter contents are not PII (filter parameters reference label keys/values, not user data). |
| Rule 14 — every new entity supports tags and labels | Constitution § Domain | ✅ Pass | This feature IS the canonical implementation that rule 14 presumes exists. Future BCs adopting tags/labels register their `entity_type` string in `common/tagging/constants.py`'s `ENTITY_TYPES` set and add the filter-parameter pass-through to their listing endpoint — no schema migration, no per-entity column. |
| Rule 18, AD-21 — residency at query time | Constitution § Domain | ✅ Pass | Tag and label rows replicate via the parent entity's existing replication path (feature 081 contract). No cross-region tag transfer; cross-entity tag search respects the user's existing residency-bounded entity visibility. |
| Rule 20 — structured JSON logs | Constitution § Domain | ✅ Pass | All new modules use `structlog`. Tag/label values are not credentials; they are organisational metadata; logged in JSON payload at INFO. |
| Rule 21 — correlation IDs propagated | Constitution § Domain | ✅ Pass | Tag/label/saved-view writes carry the existing `CorrelationContext` via FastAPI's request-scoped middleware; audit-chain entries inherit `correlation_id`, `trace_id`, `user_id`. |
| Rule 22 — Loki labels low-cardinality only | Constitution § Domain | ✅ Pass | Allowed labels: `service`, `bounded_context=common-tagging`, `level`. `entity_type` (bounded set of 7) MAY be a Loki label; `entity_id`, `tag`, `label_key`, `label_value`, `view_id` go in the JSON payload only — never as Loki labels. |
| Rule 24 — every BC dashboard | Constitution § Domain | ⚠️ Variance with rationale | Rule 24 says "every new bounded context gets a dashboard." This feature is **not** a new bounded context (it is a `common/` shared substrate); per the constitution's BC structure rule, `common/` modules do not own per-BC dashboards. The relevant operational signals (mutation rate, cross-entity tag search latency) are added as panels to the existing `platform-overview.yaml` dashboard rather than a new dashboard ConfigMap. The rule's spirit is preserved (operational signals exist); the letter doesn't strictly apply because there is no new BC. |
| Rule 25 — every BC gets E2E suite + journey crossing | Constitution § Domain | ⚠️ Variance with rationale | Same rationale as Rule 24 — this is `common/`, not a BC. E2E coverage is added by extending three existing journeys (registry-discovery, policy-authoring, operator-dashboard) to exercise the tag/label/saved-view affordances at their natural integration points; no parallel new journey is introduced (rule 28). |
| Rule 29, 30 — admin endpoint segregation, admin role gates | Constitution § Domain | ✅ Pass | Reserved-namespace label writes (where `label_key` matches `system.*` / `platform.*`) live under `/api/v1/admin/labels/reserved` and require `require_superadmin` (rule 30). All other tag/label/saved-view operations are workspace-member-RBAC and live under the constitutionally-reserved read prefixes. |
| Rule 32 — audit chain on config changes | Constitution § Domain | ✅ Pass | Every tag attach/detach, label create/update/delete, saved-view create/share/unshare/delete emits an audit-chain entry (FR-CC-2). |
| Rule 36 — UX-impacting FR documented | Constitution § Domain | ✅ Pass | Tag editor, label editor, saved-view picker affordances on each of the seven list pages are documented in the docs site as part of this PR. |
| Rule 39 — every secret resolves via SecretProvider | Constitution § Domain | ✅ N/A | This feature handles no secrets. |
| Rule 45 — backend has UI | Constitution § Domain | ✅ Pass | New `<TagEditor>`, `<LabelEditor>`, `<SavedViewPicker>` components added to each of the seven existing list pages under `apps/web/app/(main)/`. |
| Rule 47 — workspace-scoped vs platform-scoped | Constitution § Domain | ✅ Pass | Saved views are workspace-scoped when shared (visible only to members of the workspace); reserved-namespace labels are platform-scoped (visible across workspaces only to superadmin). The UI distinguishes the two scopes explicitly per rule 47. |
| Rule 48 — platform state visible | Constitution § Domain | ✅ N/A | This feature surfaces no platform-state banners. |
| Rule 50 — mock LLM for previews | Constitution § Domain | ✅ N/A | This feature does not invoke an LLM. |
| Principle I — modular monolith | Constitution § Core | ✅ Pass | All work in the Python control plane. |
| Principle III — dedicated stores | Constitution § Core | ✅ Pass | PostgreSQL for tag / label / saved-view rows. Redis for compiled-AST cache. No vector / OLAP / graph use. |
| Principle IV — no cross-BC table access | Constitution § Core | ✅ Pass | `common/tagging/` calls into the seven entity BCs ONLY via their public service interfaces (e.g., `WorkspaceService.exists`, `RegistryService.exists_agent`) for entity-existence checks during attach. The seven BCs in turn call into `TagService` / `LabelService` / `SavedViewService` via the public service interfaces. Cross-entity tag search is a single SQL query against `entity_tags` joined back through the requester's RBAC scope (which is itself resolved by calling each BC's "is visible" service interface up-front and constraining the query to that visible set — see complexity tracking entry below). |
| Principle V — append-only journal | Constitution § Core | ✅ N/A | No execution journal interaction. |
| Principle XVI — generic S3 | Constitution § Core | ✅ N/A | No object storage use. |
| Constitutional REST prefixes — already declared | Constitution § REST Prefix lines 808–810 | ✅ Pass | `/api/v1/tags/*`, `/api/v1/labels/*`, `/api/v1/saved-views/*` already in the prefix registry. Admin authoring of platform-reserved labels uses the segregated `/api/v1/admin/*` prefix per rule 29. |

## Project Structure

### Documentation (this feature)

```text
specs/082-tags-labels-saved-views/
├── plan.md                  # This file
├── spec.md                  # Feature spec
├── planning-input.md        # Verbatim brownfield input (preserved as planning artifact)
├── research.md              # Phase 0 — tag normalisation rules, label-expression grammar (BNF),
│                            #   reserved-namespace policy, orphan-owner saved-view rule,
│                            #   evaluation_runs vs evaluation_suites naming clarification
├── data-model.md            # Phase 1 — 3 PG tables + Redis AST cache key + ENTITY_TYPES set;
│                            #   cascade-on-delete contract (application-level, not FK-CASCADE)
├── quickstart.md            # Phase 1 — local end-to-end walk: tag an agent → label a policy →
│                            #   author a label-expression policy → save a view → share it
├── contracts/               # Phase 1
│   ├── tag-service.md                     # attach, detach, cascade_on_entity_deletion,
│   │                                      #   cross_entity_search, list_for_entity
│   ├── label-service.md                   # attach, update_value, detach, list_for_entity,
│   │                                      #   cascade_on_entity_deletion, filter_query;
│   │                                      #   reserved-namespace enforcement
│   ├── saved-view-service.md              # create, get, list, update, delete, share, unshare;
│   │                                      #   orphan-owner resolution rule
│   ├── label-expression-language.md       # BNF + token table + missing-key semantics + AST shape
│   ├── label-expression-evaluator.md      # parse, validate, compile_to_ast, cache_key, evaluate
│   ├── tags-rest-api.md                   # /api/v1/tags/*
│   ├── labels-rest-api.md                 # /api/v1/labels/* + /api/v1/admin/labels/reserved
│   ├── saved-views-rest-api.md            # /api/v1/saved-views/*
│   └── entity-listing-filter-extension.md # the uniform contract every entity BC's list endpoint
│                                          #   adopts: ?tags=a,b&label.env=production&label.tier=critical
├── checklists/
│   └── requirements.md
└── tasks.md                 # Created by /speckit.tasks (NOT created here)
```

### Source Code (repository root)

```text
apps/control-plane/
├── migrations/versions/
│   └── 065_tags_labels_saved_views.py                   # NEW — 3 tables (rebase to current head at merge)
└── src/platform/
    ├── common/
    │   └── tagging/                                     # NEW SHARED SUBSTRATE (rule 14 canonical)
    │       ├── __init__.py
    │       ├── constants.py                             # NEW — ENTITY_TYPES = ("workspace","agent","fleet",
    │       │                                            #   "workflow","policy","certification",
    │       │                                            #   "evaluation_run"); RESERVED_LABEL_PREFIXES =
    │       │                                            #   ("system.","platform."); MAX_TAGS_PER_ENTITY =
    │       │                                            #   50; MAX_LABELS_PER_ENTITY = 50; MAX_TAG_LEN = 128;
    │       │                                            #   MAX_LABEL_KEY_LEN = 128; MAX_LABEL_VALUE_LEN = 512;
    │       │                                            #   TAG_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")
    │       ├── models.py                                # NEW — EntityTag, EntityLabel, SavedView SQLAlchemy
    │       │                                            #   models; the (entity_type, entity_id) composite is
    │       │                                            #   the polymorphic shape — no typed FK
    │       ├── schemas.py                               # NEW — TagAttachRequest, TagDetachRequest, TagResponse,
    │       │                                            #   LabelAttachRequest, LabelResponse, LabelFilterParams,
    │       │                                            #   SavedViewCreateRequest, SavedViewResponse,
    │       │                                            #   SavedViewShareToggleRequest, CrossEntityTagSearchResponse,
    │       │                                            #   LabelExpressionValidationResponse
    │       ├── repository.py                            # NEW — PG queries: insert_tag (idempotent on conflict),
    │       │                                            #   delete_tag, list_tags_for_entity,
    │       │                                            #   list_entities_by_tag (the cross-entity search;
    │       │                                            #   takes a `visible_entity_ids_by_type` filter dict
    │       │                                            #   so RBAC is enforced at the SQL WHERE per FR-CC-1),
    │       │                                            #   upsert_label (insert or update_value), delete_label,
    │       │                                            #   list_labels_for_entity, filter_entities_by_labels
    │       │                                            #   (the JOIN-based filter the listing endpoints use),
    │       │                                            #   cascade_on_entity_deletion (deletes both tag and
    │       │                                            #   label rows in one transaction), saved_view CRUD
    │       ├── service.py                               # NEW — facade composing the three sub-services
    │       ├── tag_service.py                           # NEW — TagService class
    │       ├── label_service.py                         # NEW — LabelService class with reserved-namespace
    │       │                                            #   enforcement
    │       ├── saved_view_service.py                    # NEW — SavedViewService class with orphan-owner
    │       │                                            #   resolution rule (transfer to first active
    │       │                                            #   workspace superadmin with structured-log notice)
    │       ├── label_expression/
    │       │   ├── __init__.py
    │       │   ├── grammar.py                           # NEW — BNF documented + tokens
    │       │   ├── parser.py                            # NEW — recursive-descent parser; raises
    │       │   │                                        #   LabelExpressionSyntaxError with line+col on bad
    │       │   │                                        #   input (FR-511.18, SC-008)
    │       │   ├── ast.py                               # NEW — typed AST node classes:
    │       │   │                                        #   EqualNode, NotEqualNode, HasKeyNode,
    │       │   │                                        #   AndNode, OrNode, NotNode, GroupNode
    │       │   ├── evaluator.py                         # NEW — async evaluate(ast, target_labels: dict[str,str])
    │       │   │                                        #   -> bool; pure function over the in-memory dict;
    │       │   │                                        #   missing-key semantics specified per FR-511.20
    │       │   └── cache.py                             # NEW — Redis-backed AST cache:
    │       │                                            #   tags:label_expression_ast:{policy_id}:{version}
    │       │                                            #   plus an in-process LRU on top for steady-state
    │       │                                            #   sub-ms hits per FR-511.19, SC-009
    │       ├── router.py                                # NEW — FastAPI routers under the constitutional
    │       │                                            #   prefixes /api/v1/tags/*, /api/v1/labels/*,
    │       │                                            #   /api/v1/saved-views/*; admin reserved-label
    │       │                                            #   ops at /api/v1/admin/labels/reserved (rule 29)
    │       ├── exceptions.py                            # NEW — TagAttachLimitExceededError → 422,
    │       │                                            #   LabelAttachLimitExceededError → 422,
    │       │                                            #   InvalidTagError → 422 (pattern violation),
    │       │                                            #   ReservedLabelNamespaceError → 403,
    │       │                                            #   SavedViewNotFoundError → 404,
    │       │                                            #   LabelExpressionSyntaxError → 422,
    │       │                                            #   EntityTypeNotRegisteredError → 422
    │       ├── dependencies.py                          # NEW — FastAPI deps; reuses get_audit_chain_service
    │       │                                            #   (UPD-024), get_alert_service (feature 077)
    │       ├── filter_extension.py                      # NEW — the uniform `parse_tag_label_filters(request)`
    │       │                                            #   helper that every entity BC's listing endpoint
    │       │                                            #   uses to extract `?tags=a,b&label.env=production`
    │       │                                            #   from the query string and pass them to
    │       │                                            #   TagService / LabelService.filter_query
    │       └── visibility_resolver.py                   # NEW — resolves the requester's per-(entity_type)
    │                                                    #   visible entity-id set by calling each entity BC's
    │                                                    #   "list visible to user" service interface; used by
    │                                                    #   cross-entity tag search to enforce RBAC at the
    │                                                    #   SQL WHERE per FR-CC-1, SC-002, SC-014
    │
    ├── workspaces/
    │   ├── service.py                                   # MODIFIED — `delete` calls
    │   │                                                #   tag_service.cascade_on_entity_deletion("workspace", id)
    │   │                                                #   AND label_service.cascade_on_entity_deletion(...)
    │   │                                                #   inside the same transaction (atomic per SC-003)
    │   └── router.py                                    # MODIFIED — list-workspaces endpoint accepts
    │                                                    #   ?tags=&label.key= via filter_extension helper
    │
    ├── registry/
    │   ├── service.py                                   # MODIFIED — RegistryService.list_agents (≈ :371)
    │   │                                                #   accepts AgentDiscoveryParams extended with
    │   │                                                #   tags + labels and delegates to LabelService
    │   │                                                #   .filter_query for the JOIN; delete_agent calls
    │   │                                                #   the cascade pair atomically. The brownfield
    │   │                                                #   input named `registry/services/registry_query_service.py`
    │   │                                                #   — that file does not exist; the existing
    │   │                                                #   list_agents at :371 is the canonical filter
    │   │                                                #   site.
    │   └── router.py                                    # MODIFIED — list_agents at :147 adds tags + label
    │                                                    #   query params via filter_extension helper
    │
    ├── fleets/
    │   ├── service.py                                   # MODIFIED — same pattern: extend list endpoint;
    │   │                                                #   cascade in delete
    │   └── router.py                                    # MODIFIED — same pattern
    │
    ├── workflows/
    │   ├── service.py                                   # MODIFIED — same pattern
    │   └── router.py                                    # MODIFIED — same pattern
    │
    ├── policies/
    │   ├── service.py                                   # MODIFIED — same pattern; on policy save, parse
    │   │                                                #   any label expression and on success cache the
    │   │                                                #   compiled AST in Redis under
    │   │                                                #   tags:label_expression_ast:{policy_id}:{version}
    │   │                                                #   so the gateway hot path resolves zero DB calls
    │   │                                                #   per evaluation
    │   └── router.py                                    # MODIFIED — same pattern
    │
    ├── trust/
    │   ├── service.py                                   # MODIFIED — same pattern (TrustCertification)
    │   └── router.py                                    # MODIFIED — same pattern
    │
    ├── evaluation/
    │   ├── service.py                                   # MODIFIED — same pattern (EvaluationRun — note the
    │   │                                                #   table is `evaluation_runs`, NOT
    │   │                                                #   `evaluation_suites`; the spec/input said
    │   │                                                #   "evaluation_suites" but the actual entity model
    │   │                                                #   is EvaluationRun at evaluation/models.py:175.
    │   │                                                #   `data-model.md` documents this name choice.)
    │   └── router.py                                    # MODIFIED — same pattern
    │
    ├── governance/
    │   └── services/
    │       └── judge_service.py                         # MODIFIED — at :19 JudgeService and at :39
    │                                                    #   process_signal: after chain resolution and
    │                                                    #   before verdict generation (≈ :49), call
    │                                                    #   common/tagging/label_expression/evaluator.evaluate
    │                                                    #   with the policy's compiled AST (resolved from
    │                                                    #   Redis cache) and the target's labels (loaded
    │                                                    #   into the existing target context). The
    │                                                    #   brownfield input named
    │                                                    #   `policies/services/policy_engine.py` — that
    │                                                    #   file does not exist; this is the actual
    │                                                    #   match-condition evaluation site.
    │
    ├── common/
    │   └── (existing modules unchanged)
    │
    └── main.py                                          # MODIFIED — at :1540–1579 router-mount block:
                                                         #   app.include_router(tags_router)
                                                         #   app.include_router(labels_router)
                                                         #   app.include_router(saved_views_router)
                                                         #   No middleware added; no APScheduler jobs.

deploy/helm/observability/templates/dashboards/
└── platform-overview.yaml                               # MODIFIED — additive panels (rule 24 variance
                                                         #   rationale): tag mutation rate, label mutation
                                                         #   rate, cross-entity tag search latency,
                                                         #   compiled-AST cache hit rate. No new dashboard
                                                         #   ConfigMap.

apps/web/
├── components/features/tagging/                         # NEW — shared components reusable across
│   │                                                     #   list pages
│   ├── TagEditor.tsx                                    # NEW — chip input with autocomplete from existing
│   │                                                     #   tags in the workspace
│   ├── LabelEditor.tsx                                  # NEW — key=value pair editor; reserved-namespace
│   │                                                     #   keys disabled with tooltip for non-superadmin
│   ├── TagFilterBar.tsx                                 # NEW — filter chips for the listing toolbar;
│   │                                                     #   parses ?tags= and ?label.key= from URL
│   ├── LabelFilterPopover.tsx                           # NEW — key/value selector with values autocomplete
│   ├── SavedViewPicker.tsx                              # NEW — dropdown listing the user's saved views
│   │                                                     #   plus shared workspace views; "Save current
│   │                                                     #   view" CTA; "Share with workspace" toggle
│   ├── SavedViewSaveDialog.tsx                          # NEW — name input + share toggle + entity-type
│   │                                                     #   confirmation
│   ├── CrossEntityTagSearch.tsx                         # NEW — top-bar component for the platform shell
│   │                                                     #   (cmd+K palette extension or dedicated
│   │                                                     #   `/search?tag=` route): given a tag, returns
│   │                                                     #   visible entities grouped by type
│   └── ReservedLabelBadge.tsx                           # NEW — visual indicator on reserved-namespace
│                                                          #   labels (system.* / platform.*) so the user
│                                                          #   knows they're platform-managed and read-only
├── lib/api/tagging.ts                                   # NEW — typed wrappers over /api/v1/tags/*,
│                                                          #   /api/v1/labels/*, /api/v1/saved-views/*;
│                                                          #   TanStack Query hook factories
└── app/(main)/                                           # MODIFIED — each existing list page mounts the
    ├── agents/page.tsx                                  #   shared components in its toolbar:
    │                                                     #   <SavedViewPicker entityType="agent" />,
    │                                                     #   <TagFilterBar />, <LabelFilterPopover />,
    │                                                     #   and renders <TagEditor> + <LabelEditor>
    │                                                     #   on the agent detail row
    ├── fleet/page.tsx                                   #   same integration pattern
    ├── workflow-editor-monitor/page.tsx                 #   same integration pattern
    ├── agent-management/page.tsx                        #   same integration pattern
    ├── (admin) policies pages                           #   same integration pattern
    ├── trust-workbench/                                 #   same integration pattern (certifications)
    └── evaluation pages                                 #   same integration pattern

tests/control-plane/unit/common/tagging/
├── test_tag_service.py                                  # NEW — attach idempotency, detach, max-per-entity
│                                                          #   limit, normalisation, RBAC refusal, cascade
├── test_label_service.py                                # NEW — upsert (insert vs update_value), reserved
│                                                          #   namespace 403, max length, cascade,
│                                                          #   filter_query SQL shape
├── test_saved_view_service.py                           # NEW — CRUD, share/unshare, orphan-owner
│                                                          #   resolution rule, RBAC scoping
├── test_visibility_resolver.py                          # NEW — verifies the requester's visible-set per
│                                                          #   entity type is correctly intersected so the
│                                                          #   SQL WHERE never leaks unauthorised rows
├── test_label_expression_parser.py                      # NEW — BNF coverage; malformed inputs raise
│                                                          #   LabelExpressionSyntaxError with line+col
├── test_label_expression_evaluator.py                   # NEW — property-based test (hypothesis) over
│                                                          #   the operator set; missing-key semantics
│                                                          #   verified against the language spec
├── test_label_expression_cache.py                       # NEW — Redis cache hit, in-process LRU,
│                                                          #   invalidation on policy save
├── test_filter_extension.py                             # NEW — query-string parsing of
│                                                          #   ?tags=a,b&label.env=production
└── test_cross_entity_search_rbac.py                     # NEW — SC-002 + SC-014 — no leakage of
                                                          #   unauthorised entities

tests/control-plane/integration/common/tagging/
├── test_tag_attach_cascade_per_entity_type.py           # NEW — SC-001 + SC-003 — for each of the 7
│                                                          #   entity types, attach a tag, delete the
│                                                          #   entity, assert tag rows are gone
├── test_label_filter_per_entity_type.py                 # NEW — SC-004 — same uniform sweep across
│                                                          #   the 7 list endpoints
├── test_reserved_label_namespace_403.py                 # NEW — SC-006
├── test_label_expression_in_policy.py                   # NEW — SC-007 — author a policy with an
│                                                          #   expression; verify gateway evaluation
│                                                          #   matches/misses correctly
├── test_label_expression_malformed_save_refused.py      # NEW — SC-008 — half-broken policy not
│                                                          #   persisted
├── test_policy_gateway_latency_unchanged.py             # NEW — SC-009 — load-test comparing
│                                                          #   pre/post-feature gateway latency
├── test_saved_view_lifecycle.py                         # NEW — SC-010 — personal → share → unshare;
│                                                          #   propagation latency
├── test_saved_view_orphan_owner.py                      # NEW — SC-012 — owner leaves workspace;
│                                                          #   shared view transfers per documented rule
├── test_saved_view_stale_filter_graceful.py             # NEW — SC-011
├── test_audit_chain_emission_uniform.py                 # NEW — SC-013 — every mutation type emits an
│                                                          #   audit-chain entry
└── test_cross_entity_tag_search_rbac_end_to_end.py      # NEW — SC-002 + SC-014 — end-to-end across
                                                          #   the 7 entity types

tests/e2e/journeys/
├── test_registry_discovery_journey.py                   # MODIFIED — extend the existing journey to
│                                                          #   tag agents + label them + filter the
│                                                          #   marketplace listing by label (rule 25
│                                                          #   variance rationale: extending an existing
│                                                          #   journey rather than parallelizing per
│                                                          #   rule 28)
├── test_policy_authoring_journey.py                     # MODIFIED — extend to author a policy with
│                                                          #   a label expression and verify gateway
│                                                          #   match/miss
└── test_operator_dashboard_journey.py                   # MODIFIED — extend to save a view, share it,
                                                          #   apply it as a different user
```

**Structure Decision**: This is a `common/`-level shared substrate, not a new bounded context. The constitution's rule 14 explicitly mandates the polymorphic shape `entity_tags` / `entity_labels`, and the constitution's "common module" pattern (correlation, audit-hook, pagination, etc.) is the natural home for cross-cutting concerns that don't belong to any single BC. Each of the seven entity BCs takes a small additive change to its router (filter parameters) and service (cascade-on-delete) — no schema migration touches the entity tables themselves. The label-expression evaluator hooks into the existing match-condition flow at `governance/services/judge_service.py:19` (the actual policy-engine evaluation site, not the planning input's misnamed `policies/services/policy_engine.py`). Frontend components live in a shared `components/features/tagging/` subfolder reusable across all seven list pages. The two constitution-rule variances (rule 24, rule 25) are declared and rationalised — rule 24's "every BC dashboard" and rule 25's "every BC E2E suite" presume a new bounded context, which this is not.

## Complexity Tracking

| Item | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Polymorphic `(entity_type, entity_id)` instead of seven per-entity join tables | Constitution rule 14 explicitly mandates a polymorphic substrate ("never reinvent tagging per context"). Seven separate `agent_tags`, `workflow_tags`, `fleet_tags`, etc. tables would multiply schema migration work, query surface, and frontend integration by 7×, and would still need a coordination layer for cross-entity search. | Per-entity join tables: rejected — rule-14 violation; multiplies surface area; cross-entity search becomes a 7-way UNION ALL that does not scale. |
| Cascade-on-entity-delete enforced at the application layer (NOT FK + ON DELETE CASCADE) | A typed `FOREIGN KEY (entity_id) REFERENCES <table>(id) ON DELETE CASCADE` cannot reference seven different tables from one column. Each entity BC's existing delete path (`WorkspaceService.delete`, `RegistryService.delete_agent`, etc.) is small and already runs inside a SQLAlchemy transaction; calling `tag_service.cascade_on_entity_deletion(entity_type, id)` inside the same transaction is the cleanest atomic guarantee. | Database-level CASCADE via triggers: rejected — opaque, hard to reason about, hard to test. Per-entity FK columns added to a table with seven nullable FKs (one per entity type): rejected — sparse columns, ambiguous semantics, breaks polymorphism's central simplicity. |
| Cross-entity search resolves the requester's visible-set per entity type up-front and constrains the SQL WHERE | FR-CC-1 and SC-002 / SC-014 mandate RBAC enforcement at the SQL layer, never the response serializer. The cleanest way to honour Principle IV (no cross-BC table access) AND defence-in-depth is to ask each entity BC "what entity-ids in your domain are visible to this requester?" via that BC's existing service interface, then constrain the cross-entity tag search to that union of (entity_type, entity_id_set) pairs. The `visibility_resolver.py` module is the boundary that does this. | Cross-BC table joins (querying entity tables directly from `common/tagging/`): rejected — Principle IV violation; would also miss residency / soft-delete / per-BC visibility nuances each BC encodes. Post-filter in Python: rejected — FR-CC-1 forbids; allows an unauthorised row to leak through DB into the renderer before being dropped. |
| Compiled-AST Redis cache + in-process LRU on top | FR-511.19 + SC-009 explicitly forbid policy-gateway latency regression. The expression DSL is small, but parsing per gateway call would add tens of microseconds × the policy-cache size. Compile-once-and-cache is the standard remedy. The in-process LRU on top of Redis is needed because Redis round-trip is itself ~1 ms p95 — well above the gateway's tightest budget under burst. | Parse-on-each-call: rejected — measurable regression. Redis cache only (no in-process LRU): rejected — Redis round-trip dominates the budget under high-frequency policy evaluation. In-process LRU only (no Redis): rejected — multi-replica deployments would not invalidate consistently on policy save. Both layers together is the cheapest correct shape. |
| Hand-rolled recursive-descent parser for the label-expression DSL (vs adding `pyparsing` 3.x as a new dep) | The grammar is small (≤ 10 productions). A 200-line hand-rolled parser keeps the dependency surface clean and is easier to reason about for the malformed-input error reporting (FR-511.18 — error must point at the failing token's line+col). `pyparsing` would carry transitive complexity and a larger dependency footprint for a problem of this size. | Add `pyparsing`: rejected — extra dep for a small grammar. PEG / Lark / ANTLR: rejected — same reasoning, also overkill. Yacc/Bison-style table-driven parser: rejected — overkill. |
| Three new tables in one migration (single `065_…py`) instead of three separate migrations | The three tables are conceptually one substrate; staging them across multiple migrations would force every dev pulling main mid-feature to reason about a partial substrate (e.g., `entity_tags` exists but `entity_labels` doesn't). Keeping the substrate atomic at migration time matches how the substrate is consumed: as one unit. | Three migrations (`065_entity_tags.py`, `066_entity_labels.py`, `067_saved_views.py`): rejected — risk of partial-state confusion; rule-2 conformance is satisfied either way. |
| Each of the seven entity BCs takes a small additive listing-endpoint change (rather than a generic listing wrapper centralised in `common/`) | A central listing wrapper would have to know each BC's filter contract, RBAC rules, soft-delete semantics, and pagination shape — that's a lot of cross-BC knowledge in one place, violating Principle IV. The chosen pattern (`filter_extension.parse_tag_label_filters(request)` returning a small dataclass each entity BC's existing handler consumes) keeps the BC owning its query semantics; `common/tagging/` only owns the parameter parsing. | Centralised listing wrapper in `common/`: rejected — Principle IV violation; couples cross-BC. Per-entity duplication of the parameter-parsing logic: rejected — would drift; the helper centralises the parsing without centralising the query semantics. |
| Variance from rule 24 (every BC dashboard) and rule 25 (every BC E2E suite) — extend existing dashboards/journeys instead | Rule 24 + 25 presume a new bounded context. `common/tagging/` is shared substrate, not a BC, so the rules' letter does not apply. Extending the existing platform-overview dashboard with tag/label panels and extending three existing journeys (registry discovery, policy authoring, operator dashboard) honours the *spirit* of both rules — operational visibility exists, journey crossing exists — without inventing a free-standing surface for a substrate that has no independent operational existence. The variance is declared in the Constitution Check table rather than hidden. | Create a new "common-tagging" dashboard ConfigMap and a new "common-tagging journey": rejected — would create a dashboard that is mostly empty (the substrate has no operational state independent of the entity BCs) and a journey that artificially crosses the substrate without an authentic user goal. Rule 24/25's intent is operational visibility + journey coverage; both are achieved by extension. |

## Dependencies

- **`audit/` BC (existing)** — `AuditChainService.append` at `audit/service.py:49–72` is the canonical write path required by constitution rule 9 + 32 for every administrative action. Confirmed unchanged from UPD-024.
- **`workspaces/` BC (`workspaces/models.py:59 Workspace`)** — provides workspace membership for saved-view sharing scope; provides "list visible workspaces for user" service interface used by `visibility_resolver.py`.
- **`registry/` BC (`registry/models.py:77 AgentProfile`, `registry/service.py:371 list_agents`)** — provides "list visible agents for user" service interface; `list_agents` is the canonical filter site (NOT the brownfield input's misnamed `registry_query_service.py`); the listing endpoint at `registry/router.py:147` is the integration point for the new tag/label filter parameters.
- **`fleets/` BC (`fleets/models.py:50 Fleet`)** — same pattern.
- **`workflows/` BC (`workflows/models.py:42 WorkflowDefinition`)** — same pattern.
- **`policies/` BC (`policies/models.py:46 PolicyPolicy`)** — same pattern; additionally: on policy save the BC's service computes the compiled label-expression AST and writes it to the Redis cache.
- **`trust/` BC (`trust/models.py:91 TrustCertification`)** — same pattern.
- **`evaluation/` BC (`evaluation/models.py:175 EvaluationRun`)** — same pattern. Note the table name is `evaluation_runs`, not `evaluation_suites` as the planning input said; the `data-model.md` clarifies this.
- **`governance/` BC (`governance/services/judge_service.py:19 JudgeService`, `:39 process_signal`)** — the actual policy match-condition evaluator. The brownfield input named `policies/services/policy_engine.py` — that file does not exist; the label-expression evaluator slots in after chain resolution and before verdict generation (≈ `:49`).
- **`notifications/` BC (feature 077)** — `AlertService.process_state_change` at `notifications/service.py:203` is the routing entry point for shared-view notification ("user X shared view Y with your workspace") per FR-CC-3.
- **`security_compliance/` BC (UPD-024)** — `RotatableSecretProvider` is not used by this feature (no secrets handled). Audit chain is the only integration.
- **Constitution § REST Prefix Registry lines 808–810** — `/api/v1/tags/*`, `/api/v1/labels/*`, `/api/v1/saved-views/*` already declared; admin authoring uses the segregated `/api/v1/admin/*` prefix per rule 29.
- **Constitution rule 14** — explicitly mandates this substrate. This feature is the canonical implementation.
- **Existing FastAPI router-mount block** — `main.py:1540–1579` is where the three new routers register.
- **Existing frontend list pages** under `apps/web/app/(main)/` — each existing page mounts the shared components in its toolbar; no shared list-page abstraction is created (no list-page component exists today).
- **Redis** — already in the runtime; one new key family (`tags:label_expression_ast:*`) for the compiled-AST cache.
- **PostgreSQL** — three new tables; no extension to existing tables.

## Wave Placement

**Wave 10** — placed after notifications (feature 077, Wave 5), cost governance (079, Wave 7), incident response (080, Wave 8), and multi-region (081, Wave 9) so all integration-target BCs exist when this feature wires into them, and the seven entity BCs being tagged are stable. The brownfield input nominated **Wave 8**, but Wave 8 is too early: the saved-view picker + admin-data-table-standards integration (FR-576) presumes the seven entity BCs' list pages are stable, and the label-expression evaluator integrates into `governance/services/judge_service.py` whose own surface is settled by Wave 9. Wave 10 keeps the dependency graph clean and lets the substrate land once across all seven entity BCs in a coordinated PR rather than chasing each BC as it changes.

**Note on the input's effort estimate** — the planning input estimated 2 story points (~1 day). The plan as designed is materially larger than that:

- **3 PG tables** + Alembic migration
- **`common/tagging/` shared substrate** with services (tag, label, saved-view), repository, schemas, exceptions, dependencies, the `filter_extension` helper, the `visibility_resolver`, the entire **label-expression DSL** (grammar + parser + AST + evaluator + Redis-cached compilation)
- **3 REST router groups** (tags, labels, saved-views) + admin segregation for reserved-namespace label writes
- **7 entity BC integrations** — each is small (one router-handler tweak, one service-delete-path tweak) but multiplied by 7 it is real coordination work
- **1 governance integration** — the label-expression evaluator hook in `governance/services/judge_service.py` post-chain-resolution
- **1 policy BC integration** — compile-on-save of label expressions into the Redis AST cache
- **9 frontend components** under `components/features/tagging/` plus integration into 7 existing list pages
- **Unit + integration + property-based + E2E test coverage** to the ≥ 95% bar
- **Two operator runbooks** are NOT needed (no incident-response surface in this feature) but the docs site MUST be updated to document the label-expression DSL, the tag normalisation rules, and the reserved-namespace policy

Realistically this is ~5–8× the input's estimate. Recommend the Wave-10 split into:
- **Wave 10A**: Phase 1 + Phase 2 + Phase 3 (US1 — tags + cross-entity search, the substrate floor) — ~3 days
- **Wave 10B**: Phase 4 (US2 — labels + filtering across all 7 entity types) — ~3 days
- **Wave 10C**: Phase 5 (US3 — label-based policy expressions, the governance integration with the latency-budget guarantee) — ~3 days
- **Wave 10D**: Phase 6 + Phase 7 (US4 — saved views) and frontend integration across all 7 list pages — ~4 days
- **Wave 10E**: Phase 8 (Polish — dashboard panel additions, OpenAPI tags, lint/types/coverage, E2E journey extensions, agent-context update) — ~1 day

If the 1-day budget is firm, descope to Wave 10A only (tags + cross-entity search) and split the rest into subsequent features. The constitution's rule 14 mandate is satisfied by Wave 10A alone (the polymorphic substrate exists); labels, expressions, and saved views are valuable but not strictly required for rule-14 compliance.
