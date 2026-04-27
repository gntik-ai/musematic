# UPD-044 Repo Inventory

Date: 2026-04-28

## Active Branch

- Current branch: `094-creator-context-contracts-ui`.
- Highest migration before this feature: `071_workspace_owner_workbench.py`; UPD-044 uses `072_creator_context_contracts.py`.

## Verified Existing Surfaces

- `apps/control-plane/src/platform/context_engineering/router.py` contains the existing profile, assignment, assembly-record, drift, correlation, and A/B test endpoints. UPD-044 adds preview, versioning, rollback, and schema endpoints without removing existing routes.
- `apps/control-plane/src/platform/trust/router.py` contains existing contract CRUD, attach-interaction, attach-execution, breach, compliance, certifier, and trust endpoints. UPD-044 adds contract schema, schema-enums, preview, template listing/forking, and revision attachment.
- `apps/control-plane/src/platform/context_engineering/service.py` is extended in place with preview and versioning methods.
- `apps/control-plane/src/platform/trust/contract_service.py` is extended in place with contract preview, template fork, and revision attachment methods.
- `ContextEngineeringProfile` had no version column or version-history relationship before this feature.
- `AgentContract` had no `revision_id`/`attached_revision_id` before this feature.
- `apps/web/package.json` already includes `@monaco-editor/react` and `monaco-yaml`; `apps/web/components/features/workflows/editor/MonacoYamlEditor.tsx` is the Monaco precedent.
- `apps/web/components/features/agent-management/CompositionWizard.tsx` started with 4 steps.
- `apps/web/components/features/operator/ExecutionDrilldown.tsx` started with 4 tabs.

## Noted Divergence From Planning Text

The planning inventory claimed zero matches for mock LLM code. Current repo state includes an E2E/test helper at `apps/control-plane/src/platform/common/llm/mock_provider.py` and E2E testing wrappers. UPD-044 still introduces the creator-preview provider under `apps/control-plane/src/platform/mock_llm/` because the existing helper is Redis/E2E-oriented and not the Rule 50 creator-preview primitive.

