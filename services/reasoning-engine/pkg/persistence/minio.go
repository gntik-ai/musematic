package persistence

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
)

type ToolCallRecord struct {
	ToolName  string         `json:"tool_name"`
	Arguments map[string]any `json:"arguments,omitempty"`
	Result    string         `json:"result,omitempty"`
}

type TraceStep struct {
	StepNumber   int             `json:"step_number"`
	Type         string          `json:"type"`
	AgentFQN     string          `json:"agent_fqn,omitempty"`
	Content      string          `json:"content"`
	ToolCall     *ToolCallRecord `json:"tool_call,omitempty"`
	QualityScore float64         `json:"quality_score,omitempty"`
	TokensUsed   int64           `json:"tokens_used,omitempty"`
	Timestamp    string          `json:"timestamp,omitempty"`
}

type ConsolidatedTrace struct {
	ExecutionID            string      `json:"execution_id"`
	Technique              string      `json:"technique"`
	SchemaVersion          string      `json:"schema_version"`
	Status                 string      `json:"status"`
	Steps                  []TraceStep `json:"steps"`
	TotalTokens            int64       `json:"total_tokens"`
	ComputeBudgetUsed      float64     `json:"compute_budget_used"`
	EffectiveBudgetScope   string      `json:"effective_budget_scope,omitempty"`
	ComputeBudgetExhausted bool        `json:"compute_budget_exhausted"`
	ConsensusReached       bool        `json:"consensus_reached,omitempty"`
	Stabilized             bool        `json:"stabilized,omitempty"`
	DegradationDetected    bool        `json:"degradation_detected,omitempty"`
	CreatedAt              string      `json:"created_at,omitempty"`
	LastUpdatedAt          string      `json:"last_updated_at,omitempty"`
}

type MinIOClient struct {
	endpoint string
	bucket   string
	client   *http.Client
}

func NewMinIOClient(endpoint, bucket string) *MinIOClient {
	if endpoint == "" || bucket == "" {
		return nil
	}

	resolved := aws.ToString(aws.String(strings.TrimRight(endpoint, "/")))
	if !strings.HasPrefix(resolved, "http://") && !strings.HasPrefix(resolved, "https://") {
		resolved = "http://" + resolved
	}

	return &MinIOClient{
		endpoint: resolved,
		bucket:   bucket,
		client:   http.DefaultClient,
	}
}

func (c *MinIOClient) Upload(ctx context.Context, key string, data []byte) error {
	if c == nil {
		return nil
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPut, c.objectURL(key), bytes.NewReader(data))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/octet-stream")

	resp, err := c.client.Do(req)
	if err != nil {
		return err
	}
	defer func() {
		_ = resp.Body.Close()
	}()

	if resp.StatusCode >= http.StatusBadRequest {
		return fmt.Errorf("minio upload failed: %s", resp.Status)
	}
	return nil
}

func (c *MinIOClient) UploadTrace(
	ctx context.Context,
	executionID string,
	traceType string,
	sessionID string,
	trace ConsolidatedTrace,
) (string, error) {
	key := traceStorageKey(executionID, traceType, sessionID)
	if trace.SchemaVersion == "" {
		trace.SchemaVersion = "1.0"
	}
	if trace.ExecutionID == "" {
		trace.ExecutionID = executionID
	}
	if trace.Technique == "" {
		trace.Technique = strings.ToUpper(strings.TrimSpace(traceType))
	}
	payload, err := json.Marshal(trace)
	if err != nil {
		return "", err
	}
	if err := c.Upload(ctx, key, payload); err != nil {
		return "", err
	}
	return key, nil
}

func traceStorageKey(executionID string, traceType string, sessionID string) string {
	kind := strings.ToUpper(strings.TrimSpace(traceType))
	session := strings.TrimSpace(sessionID)
	switch kind {
	case "DEBATE":
		return fmt.Sprintf("reasoning-debates/%s/%s/trace.json", executionID, session)
	case "SELF_CORRECTION":
		return fmt.Sprintf("reasoning-corrections/%s/%s/trace.json", executionID, session)
	case "REACT":
		return fmt.Sprintf("reasoning-traces/%s/%s/react_trace.json", executionID, session)
	default:
		return fmt.Sprintf("reasoning-traces/%s/%s/trace.json", executionID, session)
	}
}

func (c *MinIOClient) GetURL(key string) string {
	if c == nil {
		return ""
	}
	return c.objectURL(key)
}

func (c *MinIOClient) objectURL(key string) string {
	escaped := strings.TrimLeft(key, "/")
	return fmt.Sprintf("%s/%s/%s", c.endpoint, url.PathEscape(c.bucket), escaped)
}
