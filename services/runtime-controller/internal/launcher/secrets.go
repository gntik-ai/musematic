package launcher

import (
	"context"
	"fmt"
	"sort"
	"strings"

	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

type KubernetesSecretResolver struct {
	Client    kubernetes.Interface
	Namespace string
}

func (r KubernetesSecretResolver) Resolve(ctx context.Context, secretRefs []string) ([]v1.VolumeProjection, []v1.EnvVar, error) {
	return ResolveSecrets(ctx, r.Client, r.Namespace, secretRefs)
}

func ResolveSecrets(ctx context.Context, client kubernetes.Interface, namespace string, secretRefs []string) ([]v1.VolumeProjection, []v1.EnvVar, error) {
	if len(secretRefs) == 0 {
		return nil, nil, nil
	}
	var projections []v1.VolumeProjection
	var envs []v1.EnvVar
	for _, secretName := range secretRefs {
		secret, err := client.CoreV1().Secrets(namespace).Get(ctx, secretName, metav1.GetOptions{})
		if err != nil {
			return nil, nil, fmt.Errorf("resolve secret %q: %w", secretName, err)
		}
		if len(secret.Data) == 0 {
			return nil, nil, fmt.Errorf("resolve secret %q: secret has no data", secretName)
		}
		keys := make([]string, 0, len(secret.Data))
		for key := range secret.Data {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		items := make([]v1.KeyToPath, 0, len(keys))
		for _, key := range keys {
			items = append(items, v1.KeyToPath{Key: key, Path: key})
			envs = append(envs, v1.EnvVar{
				Name:  "SECRETS_REF_" + toEnvKey(key),
				Value: "/run/secrets/" + key,
			})
		}
		projections = append(projections, v1.VolumeProjection{
			Secret: &v1.SecretProjection{
				LocalObjectReference: v1.LocalObjectReference{Name: secretName},
				Items:                items,
			},
		})
	}
	return projections, envs, nil
}

func toEnvKey(key string) string {
	key = strings.ReplaceAll(key, "-", "_")
	key = strings.ReplaceAll(key, ".", "_")
	return strings.ToUpper(key)
}
