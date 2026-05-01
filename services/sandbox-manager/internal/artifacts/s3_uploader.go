package artifacts

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
)

type S3Uploader struct {
	bucket   string
	endpoint string
	client   *http.Client
}

func NewS3Uploader(endpoint string, bucket string) *S3Uploader {
	if strings.TrimSpace(endpoint) == "" || strings.TrimSpace(bucket) == "" {
		return nil
	}

	return &S3Uploader{
		bucket:   strings.TrimSpace(bucket),
		endpoint: normaliseObjectStorageEndpoint(endpoint),
		client:   newS3HTTPClient(),
	}
}

func newS3HTTPClient() *http.Client {
	if transport, ok := http.DefaultTransport.(*http.Transport); ok {
		return &http.Client{Transport: transport.Clone()}
	}
	return &http.Client{Transport: http.DefaultTransport}
}

func (u *S3Uploader) Upload(ctx context.Context, key string, body io.Reader, contentType string) error {
	if u == nil {
		return nil
	}
	if contentType == "" {
		contentType = "application/octet-stream"
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPut, u.objectURL(key), body)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", contentType)

	resp, err := u.client.Do(req)
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

func normaliseObjectStorageEndpoint(endpoint string) string {
	trimmed := strings.TrimRight(strings.TrimSpace(endpoint), "/")
	if strings.HasPrefix(trimmed, "http://") || strings.HasPrefix(trimmed, "https://") {
		return trimmed
	}
	return "http://" + trimmed
}

func (u *S3Uploader) objectURL(key string) string {
	trimmed := strings.TrimLeft(key, "/")
	return fmt.Sprintf("%s/%s/%s", u.endpoint, url.PathEscape(u.bucket), trimmed)
}
