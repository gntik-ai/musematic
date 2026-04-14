package persistence

import (
	"bytes"
	"context"
	"fmt"
	"net/http"
	"net/url"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
)

type MinIOClient struct {
	bucket   string
	endpoint string
	client   *http.Client
}

func NewMinIOClient(endpoint, bucket string) *MinIOClient {
	if endpoint == "" || bucket == "" {
		return nil
	}

	resolved := normaliseEndpoint(endpoint)

	return &MinIOClient{
		bucket:   bucket,
		endpoint: resolved,
		client:   http.DefaultClient,
	}
}

func (c *MinIOClient) Upload(ctx context.Context, key string, data []byte, metadata map[string]string) error {
	if c == nil {
		return nil
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPut, c.objectURL(key), bytes.NewReader(data))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/octet-stream")
	for key, value := range metadata {
		req.Header.Set(key, value)
	}

	resp, err := c.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= http.StatusBadRequest {
		return fmt.Errorf("minio upload failed: %s", resp.Status)
	}
	return nil
}

func (c *MinIOClient) PresignGetURL(key string) string {
	if c == nil {
		return ""
	}
	return c.objectURL(key)
}

func normaliseEndpoint(endpoint string) string {
	trimmed := aws.ToString(aws.String(strings.TrimRight(endpoint, "/")))
	if strings.HasPrefix(trimmed, "http://") || strings.HasPrefix(trimmed, "https://") {
		return trimmed
	}
	return "http://" + trimmed
}

func (c *MinIOClient) objectURL(key string) string {
	trimmed := strings.TrimLeft(key, "/")
	return fmt.Sprintf("%s/%s/%s", c.endpoint, url.PathEscape(c.bucket), trimmed)
}
