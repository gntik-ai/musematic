package ate_runner

import (
	"context"
	"encoding/json"
	"fmt"

	simulationv1 "github.com/musematic/simulation-controller/api/grpc/v1"
	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

func CreateATEConfigMap(
	ctx context.Context,
	client kubernetes.Interface,
	namespace,
	sessionID string,
	scenarios []*simulationv1.ATEScenario,
	datasetRefs []string,
) (*corev1.ConfigMap, error) {
	configMap, err := BuildATEConfigMap(namespace, sessionID, scenarios, datasetRefs)
	if err != nil {
		return nil, err
	}
	return client.CoreV1().ConfigMaps(namespace).Create(ctx, configMap, metav1.CreateOptions{})
}

func DeleteATEConfigMap(ctx context.Context, client kubernetes.Interface, namespace, sessionID string) error {
	if client == nil {
		return nil
	}
	err := client.CoreV1().ConfigMaps(namespace).Delete(ctx, ateConfigMapName(sessionID), metav1.DeleteOptions{})
	if apierrors.IsNotFound(err) {
		return nil
	}
	return err
}

func BuildATEConfigMap(namespace, sessionID string, scenarios []*simulationv1.ATEScenario, datasetRefs []string) (*corev1.ConfigMap, error) {
	scenariosJSON, err := json.Marshal(scenarios)
	if err != nil {
		return nil, err
	}
	datasetRefsJSON, err := json.Marshal(datasetRefs)
	if err != nil {
		return nil, err
	}

	scorers := map[string]string{}
	for _, scenario := range scenarios {
		scorers[scenario.GetScenarioId()] = scenario.GetScorerConfig()
	}
	scorersJSON, err := json.Marshal(scorers)
	if err != nil {
		return nil, err
	}

	return &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      ateConfigMapName(sessionID),
			Namespace: namespace,
		},
		Data: map[string]string{
			"scenarios.json":     string(scenariosJSON),
			"dataset_refs.json":  string(datasetRefsJSON),
			"scorer_config.json": string(scorersJSON),
		},
	}, nil
}

func ateConfigMapName(sessionID string) string {
	return fmt.Sprintf("ate-%s", sessionID)
}
