package artifact_collector

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"path/filepath"
	"strings"

	simulationv1 "github.com/musematic/simulation-controller/api/grpc/v1"
	"github.com/musematic/simulation-controller/pkg/persistence"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/client-go/kubernetes/scheme"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/remotecommand"
)

type objectUploader interface {
	Upload(ctx context.Context, key string, data []byte, metadata map[string]string) error
}

type artifactStore interface {
	InsertSimulationArtifact(ctx context.Context, record persistence.SimulationArtifactRecord) error
}

type execFunc func(ctx context.Context, namespace, podName string, command []string) ([]byte, error)

type ExecCollector struct {
	Namespace string
	exec      execFunc
	uploader  objectUploader
	store     artifactStore
}

func NewExecCollector(namespace string, config *rest.Config, uploader objectUploader, store artifactStore) *ExecCollector {
	return &ExecCollector{
		Namespace: namespace,
		exec:      remoteExec(config),
		uploader:  uploader,
		store:     store,
	}
}

func (c *ExecCollector) Collect(ctx context.Context, simulationID, podName string, paths []string) ([]*simulationv1.ArtifactRef, bool, error) {
	if c == nil || c.exec == nil {
		return nil, false, nil
	}

	refs := make([]*simulationv1.ArtifactRef, 0, len(paths))
	partial := false
	for _, path := range paths {
		payload, err := c.exec(ctx, c.Namespace, podName, []string{"tar", "-czf", "-", path})
		if err != nil {
			if isPartialCollectionError(err) {
				partial = true
				continue
			}
			return nil, partial, err
		}

		filename := artifactFilename(path)
		key := fmt.Sprintf("%s/%s", simulationID, filename)
		metadata := map[string]string{
			"x-amz-meta-simulation":    "true",
			"x-amz-meta-simulation-id": simulationID,
			"x-amz-meta-path":          path,
		}
		if c.uploader != nil {
			if err := c.uploader.Upload(ctx, key, payload, metadata); err != nil {
				return nil, partial, err
			}
		}
		if c.store != nil {
			if err := c.store.InsertSimulationArtifact(ctx, persistence.SimulationArtifactRecord{
				SimulationID: simulationID,
				ObjectKey:    key,
				Filename:     filename,
				SizeBytes:    int64(len(payload)),
				ContentType:  "application/gzip",
			}); err != nil {
				return nil, partial, err
			}
		}
		refs = append(refs, &simulationv1.ArtifactRef{
			ObjectKey:   key,
			Filename:    filename,
			SizeBytes:   int64(len(payload)),
			ContentType: "application/gzip",
		})
	}
	return refs, partial, nil
}

func remoteExec(config *rest.Config) execFunc {
	if config == nil {
		return nil
	}

	return func(ctx context.Context, namespace, podName string, command []string) ([]byte, error) {
		coreCfg := rest.CopyConfig(config)
		coreCfg.APIPath = "/api"
		coreCfg.GroupVersion = &corev1.SchemeGroupVersion
		coreCfg.NegotiatedSerializer = scheme.Codecs.WithoutConversion()

		client, err := rest.RESTClientFor(coreCfg)
		if err != nil {
			return nil, err
		}
		execURL := client.Post().
			Namespace(namespace).
			Resource("pods").
			Name(podName).
			SubResource("exec").
			VersionedParams(&corev1.PodExecOptions{
				Command: command,
				Stdout:  true,
				Stderr:  true,
			}, scheme.ParameterCodec).
			URL()
		executor, err := remotecommand.NewSPDYExecutor(config, "POST", execURL)
		if err != nil {
			return nil, err
		}

		stdout := &bytes.Buffer{}
		stderr := &bytes.Buffer{}
		err = executor.StreamWithContext(ctx, remotecommand.StreamOptions{
			Stdout: stdout,
			Stderr: stderr,
		})
		if err != nil {
			return nil, fmt.Errorf("%w: %s", err, stderr.String())
		}
		return io.ReadAll(stdout)
	}
}

func artifactFilename(path string) string {
	trimmed := strings.TrimRight(path, "/")
	base := filepath.Base(trimmed)
	if base == "." || base == "/" || base == "" {
		base = "artifacts"
	}
	return base + ".tar.gz"
}

func isPartialCollectionError(err error) bool {
	if err == nil {
		return false
	}
	message := strings.ToLower(err.Error())
	return strings.Contains(message, "not found") || strings.Contains(message, "container") || strings.Contains(message, "unable to upgrade connection")
}
