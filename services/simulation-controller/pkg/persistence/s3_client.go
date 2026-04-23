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

type S3Client struct {
	bucket   string
	endpoint string
	client   *http.Client
}

func NewS3Client(endpoint, bucket string) *S3Client {
	if endpoint == "" || bucket == "" {
		return nil
	}

	resolved := normaliseEndpoint(endpoint)

	return &S3Client{
		bucket:   bucket,
		endpoint: resolved,
		client:   http.DefaultClient,
	}
}

func (c *S3Client) Upload(ctx context.Context, key string, data []byte, metadata map[string]string) error {
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
	defer func() {
		_ = resp.Body.Close()
	}()

	if resp.StatusCode >= http.StatusBadRequest {
		return fmt.Errorf("s3 upload failed: %s", resp.Status)
	}
	return nil
}

func (c *S3Client) PresignGetURL(key string) string {
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

func (c *S3Client) objectURL(key string) string {
	trimmed := strings.TrimLeft(key, "/")
	return fmt.Sprintf("%s/%s/%s", c.endpoint, url.PathEscape(c.bucket), trimmed)
}
