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
