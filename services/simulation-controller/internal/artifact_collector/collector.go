package artifact_collector

import (
	"context"

	simulationv1 "github.com/musematic/simulation-controller/api/grpc/v1"
)

type ArtifactCollector interface {
	Collect(ctx context.Context, simulationID, podName string, paths []string) ([]*simulationv1.ArtifactRef, bool, error)
}
