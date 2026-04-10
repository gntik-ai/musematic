CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE simulations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id UUID NOT NULL UNIQUE,
    agent_image TEXT NOT NULL,
    agent_config_json JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL CHECK (status IN ('CREATING','RUNNING','COMPLETED','FAILED','TERMINATED')),
    namespace TEXT NOT NULL DEFAULT 'platform-simulation',
    pod_name TEXT,
    cpu_request TEXT NOT NULL DEFAULT '500m',
    memory_request TEXT NOT NULL DEFAULT '512Mi',
    max_duration_seconds INTEGER NOT NULL DEFAULT 3600,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    terminated_at TIMESTAMPTZ,
    error_message TEXT
);

CREATE INDEX idx_simulations_status ON simulations (status);
CREATE INDEX idx_simulations_created_at ON simulations (created_at);

CREATE TABLE simulation_artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id UUID NOT NULL REFERENCES simulations(simulation_id) ON DELETE CASCADE,
    object_key TEXT NOT NULL,
    filename TEXT NOT NULL,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_simulation_artifacts_simulation_id ON simulation_artifacts (simulation_id);

CREATE TABLE ate_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL UNIQUE,
    simulation_id UUID NOT NULL REFERENCES simulations(simulation_id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    scenarios_json JSONB NOT NULL,
    report_object_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_ate_sessions_simulation_id ON ate_sessions (simulation_id);

CREATE TABLE ate_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES ate_sessions(session_id) ON DELETE CASCADE,
    scenario_id TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    quality_score DOUBLE PRECISION,
    latency_ms INTEGER,
    cost DOUBLE PRECISION,
    safety_compliant BOOLEAN,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (session_id, scenario_id)
);

CREATE INDEX idx_ate_results_session_id ON ate_results (session_id);
