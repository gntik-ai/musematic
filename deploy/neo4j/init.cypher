// Uniqueness constraints on core entity ID fields
CREATE CONSTRAINT agent_id IF NOT EXISTS FOR (a:Agent) REQUIRE a.id IS UNIQUE;
CREATE CONSTRAINT workflow_id IF NOT EXISTS FOR (w:Workflow) REQUIRE w.id IS UNIQUE;
CREATE CONSTRAINT fleet_id IF NOT EXISTS FOR (f:Fleet) REQUIRE f.id IS UNIQUE;
CREATE CONSTRAINT hypothesis_id IF NOT EXISTS FOR (h:Hypothesis) REQUIRE h.id IS UNIQUE;
CREATE CONSTRAINT memory_id IF NOT EXISTS FOR (m:Memory) REQUIRE m.id IS UNIQUE;

// Performance indexes
CREATE INDEX memory_workspace IF NOT EXISTS FOR (m:Memory) ON (m.workspace_id);
CREATE INDEX evidence_hypothesis IF NOT EXISTS FOR (e:Evidence) ON (e.hypothesis_id);
CREATE INDEX relationship_type IF NOT EXISTS FOR ()-[r:RELATES_TO]-() ON (r.type);
