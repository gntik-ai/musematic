package state

import (
	"bytes"
	"context"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

type S3PutObjectClient interface {
	PutObject(context.Context, *s3.PutObjectInput, ...func(*s3.Options)) (*s3.PutObjectOutput, error)
}

type S3TaskPlanUploader struct {
	Client S3PutObjectClient
	Bucket string
}

func (u S3TaskPlanUploader) UploadTaskPlan(ctx context.Context, key string, body []byte) error {
	_, err := u.Client.PutObject(ctx, &s3.PutObjectInput{
		Bucket:      aws.String(u.Bucket),
		Key:         aws.String(key),
		Body:        bytes.NewReader(body),
		ContentType: aws.String("application/json"),
	})
	return err
}
