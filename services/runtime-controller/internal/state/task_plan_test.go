package state

import (
	"bytes"
	"context"
	"testing"

	"github.com/aws/aws-sdk-go-v2/service/s3"
)

type fakeTaskPlanUploader struct {
	key  string
	body []byte
	err  error
}

func (f *fakeTaskPlanUploader) UploadTaskPlan(_ context.Context, key string, body []byte) error {
	f.key = key
	f.body = append([]byte(nil), body...)
	return f.err
}

func TestPrepareTaskPlanRecordKeepsSmallPayloadInline(t *testing.T) {
	store := &Store{}
	record, err := store.prepareTaskPlanRecord(context.Background(), TaskPlanRecord{
		ExecutionID: "exec-1",
		StepID:      "step-1",
		PayloadJSON: []byte(`{"small":true}`),
	})
	if err != nil {
		t.Fatalf("prepareTaskPlanRecord returned error: %v", err)
	}
	if record.PayloadObjectKey != "" || string(record.PayloadJSON) != `{"small":true}` {
		t.Fatalf("small payload should remain inline: %+v", record)
	}
}

func TestPrepareTaskPlanRecordUploadsLargePayload(t *testing.T) {
	uploader := &fakeTaskPlanUploader{}
	store := &Store{TaskPlanUploader: uploader}
	payload := bytes.Repeat([]byte("x"), 65537)

	record, err := store.prepareTaskPlanRecord(context.Background(), TaskPlanRecord{
		ExecutionID: "exec-1",
		StepID:      "step-7",
		PayloadJSON: payload,
	})
	if err != nil {
		t.Fatalf("prepareTaskPlanRecord returned error: %v", err)
	}
	if record.PayloadObjectKey != "task-plans/exec-1/step-7.json" {
		t.Fatalf("unexpected object key: %q", record.PayloadObjectKey)
	}
	if len(record.PayloadJSON) != 0 || !bytes.Equal(uploader.body, payload) {
		t.Fatalf("large payload should be uploaded and removed from inline column")
	}
}

type fakeS3Client struct {
	input *s3.PutObjectInput
}

func (f *fakeS3Client) PutObject(_ context.Context, input *s3.PutObjectInput, _ ...func(*s3.Options)) (*s3.PutObjectOutput, error) {
	f.input = input
	return &s3.PutObjectOutput{}, nil
}

func TestS3TaskPlanUploaderPutsJSONObject(t *testing.T) {
	client := &fakeS3Client{}
	uploader := S3TaskPlanUploader{Client: client, Bucket: "bucket-a"}

	if err := uploader.UploadTaskPlan(context.Background(), "task-plans/exec/step.json", []byte(`{"ok":true}`)); err != nil {
		t.Fatalf("UploadTaskPlan returned error: %v", err)
	}
	if client.input == nil || *client.input.Bucket != "bucket-a" || *client.input.Key != "task-plans/exec/step.json" {
		t.Fatalf("unexpected put object input: %+v", client.input)
	}
	if client.input.ContentType == nil || *client.input.ContentType != "application/json" {
		t.Fatalf("expected application/json content type")
	}
}
