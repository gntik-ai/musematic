# Feature Specification: Agent Catalog and Creator Workbench

**Feature Branch**: `041-agent-catalog-workbench`  
**Created**: 2026-04-16  
**Status**: Draft  
**Input**: User description for agent catalog with DataTable, agent detail with lifecycle management, drag-and-drop upload, metadata editor, revision timeline, health score gauge, and AI-assisted composition wizard.  
**Requirements Traceability**: FEAT-FE-006

## User Scenarios & Testing

### User Story 1 - Browse and Search Agent Catalog (Priority: P1)

A platform operator opens the agent catalog to find a specific agent or browse all registered agents. They see a searchable, sortable data table showing each agent's name, namespace, maturity level (as a colored badge), current status (active, draft, archived), number of revisions, and last updated date. They can filter by maturity level, status, or namespace. Clicking an agent row navigates to its detail page.

**Why this priority**: Without the ability to browse and discover agents, no other workbench capability (editing, uploading, composing) has a meaningful entry point. This is the foundational navigation surface.

**Independent Test**: Open the agent catalog page. Confirm a data table renders with columns: name, namespace, maturity badge, status, revision count, last updated. Type a search term — confirm the table filters. Sort by name — confirm ordering changes. Filter by maturity "production" — confirm only matching agents shown. Click a row — confirm navigation to agent detail.

**Acceptance Scenarios**:

1. **Given** 50 registered agents, **When** the operator opens the catalog, **Then** a data table renders with all agents in pages (default 20 per page) showing name, namespace, maturity badge (color-coded), status, revision count, and last updated timestamp.
2. **Given** the catalog is open, **When** the operator types "kyc" in the search field, **Then** the table filters within 300ms to show only agents whose name or namespace contains "kyc".
3. **Given** the catalog is open, **When** the operator selects filter "maturity: production" and "status: active", **Then** only agents matching both criteria are shown.
4. **Given** a filtered catalog, **When** the operator clicks an agent row, **Then** the browser navigates to that agent's detail page showing its full information.

---

### User Story 2 - View Agent Detail and Health Score (Priority: P1)

The operator views a specific agent's detail page, which serves as the central hub for all agent management activities. The page shows the agent's metadata (name, namespace, FQN, description, tags, category, maturity level), a composite health score gauge, bound policies, active certifications, evaluation results summary, and a revision timeline. Each section is accessible but the page loads quickly by deferring non-critical sections.

**Why this priority**: The detail page is the operational center — it gates access to editing, revision management, and publication. Without it, operators cannot inspect or manage individual agents.

**Independent Test**: Navigate to an agent detail page. Confirm metadata section shows all fields. Confirm health score gauge renders with a composite score. Confirm policies, certifications, and evaluations sections are present. Confirm revision timeline shows at least the current revision with timestamp and author.

**Acceptance Scenarios**:

1. **Given** a registered agent, **When** the operator navigates to its detail page, **Then** the page displays: FQN (namespace:name), description, tags, category, maturity badge, status, and current revision number.
2. **Given** an agent with health data, **When** the detail page loads, **Then** a composite health score gauge renders showing a score from 0–100 with color coding (red < 40, yellow 40–70, green > 70) and a breakdown tooltip showing component scores.
3. **Given** an agent with bound policies, **When** the operator views the policies section, **Then** each policy name, type, and enforcement status is listed.
4. **Given** an agent with 5 revisions, **When** the operator views the revision timeline, **Then** all 5 revisions are shown chronologically with revision number, timestamp, author, and a summary of changes.

---

### User Story 3 - Upload Agent Package (Priority: P2)

The operator uploads a new agent package (.tar.gz or .zip) via drag-and-drop or file picker. A progress bar shows upload status. After upload completes, the system extracts and validates the package contents, reporting any errors. If valid, the agent appears in the catalog as a draft awaiting metadata completion and publication.

**Why this priority**: Upload is the primary ingestion path for new agents. It builds on the catalog (US1) and detail page (US2) as the destination for uploaded agents. Without upload, the only way to add agents is through the composition wizard (US7).

**Independent Test**: Drag a valid .tar.gz file onto the upload zone. Confirm progress bar appears and advances. Confirm upload completes with a success message. Confirm the new agent appears in the catalog as a draft. Try uploading an invalid file — confirm an error message with specific reasons is shown.

**Acceptance Scenarios**:

1. **Given** the agent upload interface, **When** the operator drags a valid .tar.gz file onto the drop zone, **Then** a progress bar appears showing upload percentage, and upon completion a success notification shows with a link to the new draft agent.
2. **Given** the upload interface, **When** the operator clicks the file picker button, **Then** a file dialog opens filtered to .tar.gz and .zip files only.
3. **Given** an uploaded package with missing required fields, **When** validation runs, **Then** the system displays specific validation errors (e.g., "missing agent.yaml", "invalid schema version") and does not create a draft agent.
4. **Given** a large file (>50MB), **When** the operator uploads it, **Then** the upload shows real-time progress and supports cancellation via a cancel button during upload.

---

### User Story 4 - Edit Agent Metadata (Priority: P2)

The operator edits an agent's metadata using a structured form: name, description, tags (multi-select), category, maturity level, reasoning modes (multi-select), namespace (selected from available namespaces), local name (combined with namespace to preview the FQN), purpose (mandatory, minimum 20 characters), approach (optional, multi-line), role type (executor, planner, orchestrator, observer, judge, enforcer, or custom), and visibility configuration (add/remove FQN patterns for visible agents and tools). Changes are validated in real-time and saved explicitly.

**Why this priority**: Metadata editing is required before an agent can be published. It depends on the detail page (US2) existing but is itself a prerequisite for publication (US5). This is the primary agent configuration surface.

**Independent Test**: Open an agent's metadata editor. Change the description — confirm real-time validation passes. Clear the purpose field — confirm validation error appears immediately. Change the namespace — confirm FQN preview updates. Add a visibility pattern — confirm it appears in the list. Save — confirm changes persist and detail page reflects updates.

**Acceptance Scenarios**:

1. **Given** an agent in draft status, **When** the operator opens the metadata editor, **Then** all fields are editable with current values pre-filled, and the FQN preview shows `{namespace}:{local_name}` updating live as either field changes.
2. **Given** the metadata editor, **When** the operator clears the purpose field, **Then** an inline validation error appears immediately: "Purpose is required (minimum 20 characters)".
3. **Given** the metadata editor, **When** the operator selects a role type from the dropdown (6 predefined + custom), **Then** the selection is reflected immediately and if "custom" is selected, a free-text input appears for the custom role name.
4. **Given** the visibility configuration section, **When** the operator adds a pattern "finance-ops:*", **Then** the pattern appears in the list and a preview shows which agents and tools would become visible under that pattern.
5. **Given** valid changes, **When** the operator clicks save, **Then** changes are persisted, the detail page reflects the updates, and a success notification is shown.

---

### User Story 5 - Publish Agent Through Lifecycle Workflow (Priority: P2)

The operator publishes an agent through a structured lifecycle: draft → validate → publish. From the detail page, the operator clicks "Validate" to run automated checks (schema compliance, required fields, policy conformance). If validation passes, the "Publish" button becomes active. Clicking "Publish" shows a confirmation dialog summarizing what will change (visibility, availability to other agents/users). After confirmation, the agent transitions to "active" status.

**Why this priority**: Publication is the gate between internal development and production availability. It depends on metadata editing (US4) being complete and validation passing, making it a natural follow-on.

**Independent Test**: Open a draft agent detail page. Click "Validate" — confirm validation runs and reports results. Fix any issues if needed. Confirm "Publish" button becomes active after validation passes. Click "Publish" — confirm a summary dialog appears. Confirm — confirm agent status changes to "active" and it appears in the marketplace.

**Acceptance Scenarios**:

1. **Given** a draft agent with incomplete metadata, **When** the operator clicks "Validate", **Then** validation results show specific failures (e.g., "missing purpose field", "no policies bound") and the "Publish" button remains disabled.
2. **Given** a draft agent with all required metadata, **When** the operator clicks "Validate" and all checks pass, **Then** a green checkmark appears next to "Validation" and the "Publish" button becomes active.
3. **Given** a validated agent, **When** the operator clicks "Publish", **Then** a confirmation dialog shows: agent FQN, what workspaces will see it, what changes from current state, and asks for explicit confirmation.
4. **Given** the confirmation dialog, **When** the operator confirms, **Then** the agent status transitions to "active", the detail page updates to reflect the new status, and a success notification appears.

---

### User Story 6 - View and Compare Revisions (Priority: P3)

The operator views the full revision history of an agent as a timeline. Each revision shows its number, timestamp, author, status, and a change summary. The operator can select any two revisions to view a side-by-side diff showing what changed between them — including metadata changes, configuration changes, and code changes. The operator can also roll back to a previous revision.

**Why this priority**: Revision management is important for audit and rollback but only becomes valuable after agents have been edited (US4) and published (US5) multiple times. It is a power-user feature that improves operational confidence.

**Independent Test**: Open an agent with 3+ revisions. Confirm timeline shows all revisions with metadata. Select revision 1 and revision 3. Confirm a diff view shows changes between them. Click "Rollback to revision 1" — confirm a new revision is created that matches revision 1's state.

**Acceptance Scenarios**:

1. **Given** an agent with 5 revisions, **When** the operator opens the revision timeline, **Then** all revisions are listed chronologically with: revision number, creation timestamp, author name, status at that time, and a brief change summary.
2. **Given** the revision timeline, **When** the operator selects two revisions for comparison, **Then** a side-by-side diff view shows all differences: metadata field changes, configuration changes, and any code changes with additions highlighted in green and removals in red.
3. **Given** a revision diff, **When** the operator clicks "Rollback to revision N", **Then** a confirmation dialog warns about the rollback impact, and upon confirmation a new revision is created that copies the selected revision's state, preserving the full revision history.

---

### User Story 7 - Create Agent via AI Composition Wizard (Priority: P3)

The operator creates a new agent using an AI-assisted 4-step wizard. Step 1: the operator describes what the agent should do in natural language. Step 2: the AI generates a blueprint showing proposed configuration (model, tools, connectors, policies, context profile) with visible reasoning explaining each choice. Step 3: the operator customizes the blueprint — modifying any proposed value, adding or removing tools, changing the model. Step 4: the system validates the customized blueprint against platform constraints and creates the agent as a draft. The wizard provides an alternative path to manual upload (US3) for users who prefer describing intent over packaging code.

**Why this priority**: The composition wizard is the highest-value UX innovation but depends on the catalog (US1), detail page (US2), and metadata editing (US4) to provide the destination for created agents. It also requires backend AI composition capabilities to be available.

**Independent Test**: Open the composition wizard. Describe "an agent that monitors financial transactions for fraud." Confirm the AI generates a blueprint with model, tools, and policies. Modify one tool selection. Click "Validate" — confirm validation runs. Click "Create" — confirm a draft agent appears in the catalog with the configured blueprint.

**Acceptance Scenarios**:

1. **Given** the composition wizard step 1, **When** the operator enters "an agent that monitors financial transactions for fraud", **Then** a loading indicator appears and within 30 seconds the AI returns a blueprint.
2. **Given** a generated blueprint in step 2, **When** the operator reviews it, **Then** each recommended tool, model setting, connector, and policy shows the AI's reasoning for that choice, and a confidence indicator shows how certain the AI is about each recommendation.
3. **Given** the customization step 3, **When** the operator removes a recommended tool and adds a different one, **Then** the blueprint updates to reflect the change and a warning appears if the modification may affect the agent's ability to fulfill the described purpose.
4. **Given** a customized blueprint in step 4, **When** validation passes, **Then** the "Create Agent" button becomes active, and clicking it creates a draft agent with the blueprint configuration pre-filled in its metadata.

---

### Edge Cases

- What happens when the operator uploads an agent with the same FQN as an existing agent? The system warns that the upload will create a new revision of the existing agent, not a new agent, and asks for confirmation.
- What happens when validation fails during publication? The agent remains in draft status. Specific failures are listed with links to the relevant metadata fields for correction.
- What happens when the AI composition wizard returns a low-confidence blueprint? Recommendations with confidence below 50% are highlighted in yellow with a note explaining the uncertainty and suggesting the operator review carefully.
- How does the system handle concurrent edits to the same agent by two operators? The system uses optimistic locking — if a save conflicts with a newer change, the operator sees the other person's changes and is asked to merge or overwrite.
- What happens when the operator attempts to roll back to a revision that references tools or policies that no longer exist? The rollback warns about deprecated references and prevents activation until they are resolved.
- What happens when the upload zone receives an unsupported file type? An inline error message appears immediately: "Unsupported file type. Only .tar.gz and .zip files are accepted."
- What happens if the AI composition service is unavailable? The wizard shows an error message on step 2 with a "Retry" button and a link to the manual upload path.

## Requirements

### Functional Requirements

- **FR-001**: System MUST display a searchable, sortable, paginated data table of all agents with columns: name, namespace, maturity badge, status, revision count, and last updated
- **FR-002**: System MUST support filtering agents by maturity level, status, namespace, and free-text search with results appearing within 300ms of input
- **FR-003**: System MUST provide an agent detail page showing full metadata, composite health score gauge, bound policies, certifications, evaluations summary, and revision timeline
- **FR-004**: Health score gauge MUST display a 0–100 composite score with color coding (red < 40, yellow 40–70, green > 70) and component score breakdown on hover
- **FR-005**: System MUST support drag-and-drop and file picker upload of .tar.gz and .zip agent packages with real-time progress indication
- **FR-006**: System MUST validate uploaded packages and report specific errors; valid packages become draft agents
- **FR-007**: System MUST provide a structured metadata editor with fields: name, description, tags, category, maturity, reasoning modes, purpose (mandatory, min 20 chars), approach (optional), and role type (7 options including custom)
- **FR-008**: Metadata editor MUST include FQN configuration: namespace selector + local name input with live FQN preview
- **FR-009**: Metadata editor MUST include a visibility configuration panel for adding/removing FQN patterns that grant visibility to other agents and tools
- **FR-010**: System MUST validate metadata in real-time as the operator types, showing inline errors for constraint violations
- **FR-011**: System MUST support a publication lifecycle: draft → validate (automated checks) → publish (with confirmation dialog)
- **FR-012**: Validation MUST check schema compliance, required field completeness, and policy conformance before enabling publication
- **FR-013**: Publication confirmation dialog MUST summarize visibility impact, affected workspaces, and what changes from the current published state
- **FR-014**: System MUST display a chronological revision timeline with revision number, timestamp, author, status, and change summary
- **FR-015**: System MUST support side-by-side diff comparison between any two selected revisions showing metadata, configuration, and code changes
- **FR-016**: System MUST support rollback to a previous revision, creating a new revision preserving the full history
- **FR-017**: AI composition wizard MUST guide the operator through 4 steps: describe → review blueprint → customize → validate and create
- **FR-018**: Blueprint review step MUST show the AI's reasoning for each recommendation and a confidence indicator per suggestion
- **FR-019**: Customization step MUST warn the operator when modifications may affect the agent's ability to fulfill the described purpose
- **FR-020**: All interfaces MUST be keyboard navigable and screen reader compatible
- **FR-021**: All interfaces MUST render correctly in both light and dark mode
- **FR-022**: All interfaces MUST be responsive across mobile and desktop viewport sizes
- **FR-023**: System MUST handle concurrent edits with optimistic locking and conflict resolution UI
- **FR-024**: Upload MUST support cancellation during progress and reject unsupported file types with clear error messages

### Key Entities

- **AgentCatalogEntry**: A row in the catalog data table — agent name, namespace, FQN, maturity badge, status, revision count, last updated. Serves as the summary view linking to the detail page.
- **AgentDetail**: The full agent record including metadata, health score, policies, certifications, evaluations, and revision timeline. The central management hub for an individual agent.
- **AgentRevision**: A versioned snapshot of an agent's complete state — configuration, metadata, and code at a point in time. Supports comparison and rollback.
- **AgentHealthScore**: A composite 0–100 score derived from evaluation results, behavioral metrics, certification status, and policy conformance. Displayed as a gauge with component breakdown.
- **CompositionBlueprint**: An AI-generated agent configuration proposal including model, tools, connectors, policies, and context profile with per-item reasoning and confidence. The intermediate artifact in the composition wizard.
- **VisibilityPattern**: An FQN pattern (exact or wildcard like "finance-ops:*") granting the agent visibility to specific other agents and tools. Configurable per agent.

## Success Criteria

### Measurable Outcomes

- **SC-001**: An operator can find a specific agent in the catalog (search + click) within 10 seconds for a catalog of 100+ agents
- **SC-002**: Agent detail page loads and displays all sections within 2 seconds, with health score gauge visible on initial render
- **SC-003**: Upload completes with progress indication for packages up to 50MB, with validation results shown within 5 seconds of upload completion
- **SC-004**: Metadata changes are validated in real-time — errors appear within 200ms of input
- **SC-005**: The full publication workflow (validate → review → confirm) completes within 30 seconds for a fully prepared agent
- **SC-006**: Revision comparison (diff view) renders within 3 seconds for any pair of revisions
- **SC-007**: AI composition wizard returns a blueprint within 30 seconds of the operator submitting a description, and the full wizard (all 4 steps) completes within 3 minutes
- **SC-008**: All interfaces pass WCAG 2.1 AA accessibility audit
- **SC-009**: All interfaces render correctly in both light and dark mode with no visual artifacts

## Assumptions

- Backend APIs for agent registry, composition, policy evaluation, and trust certification are available and operational (features 021, 028, 032, 038)
- Agent package format (.tar.gz/.zip) follows the platform's established packaging schema including an `agent.yaml` manifest
- The AI composition service (feature 038) handles blueprint generation; this feature only provides the frontend wizard interface
- Health score computation happens on the backend; this feature displays the pre-computed score
- "Reasoning modes" refer to the platform's supported reasoning engine modes (chain-of-thought, tree-of-thought, etc.) — the metadata editor presents them as a multi-select
- The revision diff operates on structured data (JSON/YAML fields); binary diff for code files is out of scope for v1
- Optimistic locking for concurrent edits uses standard HTTP conditional headers (If-Unmodified-Since / 412 conflict pattern)
- Mobile responsiveness means usable on tablet-sized screens; the composition wizard and diff view may use simplified layouts on screens below 768px
