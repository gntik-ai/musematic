CREATE TABLE reasoning_traces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id UUID NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('DIRECT','CHAIN_OF_THOUGHT','TREE_OF_THOUGHT','REACT','CODE_AS_REASONING','DEBATE')),
    total_events INTEGER NOT NULL DEFAULT 0,
    dropped_events INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    object_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_reasoning_traces_execution_id ON reasoning_traces (execution_id);

CREATE TABLE reasoning_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id UUID NOT NULL REFERENCES reasoning_traces(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    sequence_num INTEGER NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    payload_size INTEGER NOT NULL DEFAULT 0,
    object_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_reasoning_events_trace_id ON reasoning_events (trace_id);
CREATE INDEX idx_reasoning_events_occurred_at ON reasoning_events (occurred_at);

CREATE TABLE tot_branches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tree_id UUID NOT NULL,
    branch_id UUID NOT NULL UNIQUE,
    hypothesis TEXT NOT NULL,
    quality_score DOUBLE PRECISION,
    token_cost INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK (status IN ('CREATED','ACTIVE','COMPLETED','PRUNED','FAILED')),
    object_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_tot_branches_tree_id ON tot_branches (tree_id);

CREATE TABLE correction_iterations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    loop_id UUID NOT NULL,
    iteration_num INTEGER NOT NULL,
    quality_score DOUBLE PRECISION NOT NULL,
    delta DOUBLE PRECISION,
    cost DOUBLE PRECISION NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (loop_id, iteration_num)
);

CREATE INDEX idx_correction_iterations_loop_id ON correction_iterations (loop_id);
