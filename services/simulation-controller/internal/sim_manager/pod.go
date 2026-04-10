package sim_manager

import (
	"context"
	"fmt"

	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

type PodManager struct {
	Client             kubernetes.Interface
	Namespace          string
	Bucket             string
	DefaultMaxDuration int32
}

func NewPodManager(client kubernetes.Interface, namespace, bucket string, defaultMaxDuration int32) *PodManager {
	if namespace == "" {
		namespace = DefaultNamespace
	}
	if bucket == "" {
		bucket = DefaultBucket
	}
	if defaultMaxDuration <= 0 {
		defaultMaxDuration = DefaultMaxDurationSec
	}
	return &PodManager{
		Client:             client,
		Namespace:          namespace,
		Bucket:             bucket,
		DefaultMaxDuration: defaultMaxDuration,
	}
}

func (m *PodManager) CreatePod(ctx context.Context, spec SimulationPodSpec) (*corev1.Pod, error) {
	if m == nil || m.Client == nil {
		return nil, fmt.Errorf("kubernetes client is not configured")
	}

	pod, err := BuildPod(spec, m.Namespace, m.Bucket, m.DefaultMaxDuration)
	if err != nil {
		return nil, err
	}
	return m.Client.CoreV1().Pods(pod.Namespace).Create(ctx, pod, metav1.CreateOptions{})
}

func (m *PodManager) DeletePod(ctx context.Context, podName string) error {
	if m == nil || m.Client == nil {
		return fmt.Errorf("kubernetes client is not configured")
	}

	grace := int64(10)
	err := m.Client.CoreV1().Pods(m.Namespace).Delete(ctx, podName, metav1.DeleteOptions{
		GracePeriodSeconds: &grace,
	})
	if apierrors.IsNotFound(err) {
		return nil
	}
	return err
}

func (m *PodManager) GetPodPhase(ctx context.Context, podName string) (string, error) {
	if m == nil || m.Client == nil {
		return "", fmt.Errorf("kubernetes client is not configured")
	}

	pod, err := m.Client.CoreV1().Pods(m.Namespace).Get(ctx, podName, metav1.GetOptions{})
	if err != nil {
		return "", err
	}
	return string(pod.Status.Phase), nil
}

func BuildPod(spec SimulationPodSpec, defaultNamespace, defaultBucket string, defaultMaxDuration int32) (*corev1.Pod, error) {
	namespace := firstNonEmpty(spec.Namespace, defaultNamespace, DefaultNamespace)
	bucket := firstNonEmpty(spec.Bucket, defaultBucket, DefaultBucket)
	maxDuration := spec.MaxDurationSeconds
	if maxDuration <= 0 {
		maxDuration = defaultMaxDuration
		if maxDuration <= 0 {
			maxDuration = DefaultMaxDurationSec
		}
	}

	resources, err := buildResources(spec)
	if err != nil {
		return nil, err
	}

	podName := fmt.Sprintf("sim-%s", spec.SimulationID)
	env := []corev1.EnvVar{
		{Name: "SIMULATION", Value: "true"},
		{Name: "SIMULATION_ID", Value: spec.SimulationID},
		{Name: "SIMULATION_BUCKET", Value: bucket},
		{Name: "SIMULATION_ARTIFACTS_PREFIX", Value: spec.SimulationID},
	}
	for key, value := range spec.AgentEnv {
		env = append(env, corev1.EnvVar{Name: key, Value: value})
	}

	volumes := []corev1.Volume{
		{Name: "output", VolumeSource: corev1.VolumeSource{EmptyDir: &corev1.EmptyDirVolumeSource{SizeLimit: quantityPtr("512Mi")}}},
		{Name: "workspace", VolumeSource: corev1.VolumeSource{EmptyDir: &corev1.EmptyDirVolumeSource{SizeLimit: quantityPtr("1Gi")}}},
		{Name: "tmp", VolumeSource: corev1.VolumeSource{EmptyDir: &corev1.EmptyDirVolumeSource{SizeLimit: quantityPtr("256Mi")}}},
	}
	volumeMounts := []corev1.VolumeMount{
		{Name: "output", MountPath: "/output"},
		{Name: "workspace", MountPath: "/workspace"},
		{Name: "tmp", MountPath: "/tmp"},
	}
	if spec.ATEConfigMapName != "" {
		volumes = append(volumes, corev1.Volume{
			Name: "ate-config",
			VolumeSource: corev1.VolumeSource{
				ConfigMap: &corev1.ConfigMapVolumeSource{
					LocalObjectReference: corev1.LocalObjectReference{Name: spec.ATEConfigMapName},
				},
			},
		})
		volumeMounts = append(volumeMounts, corev1.VolumeMount{Name: "ate-config", MountPath: "/ate", ReadOnly: true})
		env = append(env,
			corev1.EnvVar{Name: "ATE_SESSION_ID", Value: spec.ATESessionID},
			corev1.EnvVar{Name: "ATE_SCENARIOS_PATH", Value: "/ate/scenarios.json"},
		)
	}

	return &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      podName,
			Namespace: namespace,
			Labels: map[string]string{
				"app":                "simulation-pod",
				SimulationLabelKey:   "true",
				SimulationIDLabelKey: spec.SimulationID,
			},
			Annotations: map[string]string{
				"simulation-created-by": "simulation-controller",
			},
		},
		Spec: corev1.PodSpec{
			ServiceAccountName:           "simulation-pod-sa",
			AutomountServiceAccountToken: boolPtr(false),
			EnableServiceLinks:           boolPtr(false),
			RestartPolicy:                corev1.RestartPolicyNever,
			ActiveDeadlineSeconds:        int64Ptr(int64(maxDuration)),
			SecurityContext: &corev1.PodSecurityContext{
				RunAsNonRoot: boolPtr(true),
				RunAsUser:    int64Ptr(65534),
				FSGroup:      int64Ptr(65534),
			},
			Containers: []corev1.Container{{
				Name:            "simulation",
				Image:           spec.AgentImage,
				ImagePullPolicy: corev1.PullIfNotPresent,
				Env:             env,
				Resources:       resources,
				SecurityContext: &corev1.SecurityContext{
					AllowPrivilegeEscalation: boolPtr(false),
					ReadOnlyRootFilesystem:   boolPtr(true),
					RunAsNonRoot:             boolPtr(true),
					RunAsUser:                int64Ptr(65534),
					Capabilities:             &corev1.Capabilities{Drop: []corev1.Capability{"ALL"}},
				},
				VolumeMounts: volumeMounts,
			}},
			Volumes: volumes,
		},
	}, nil
}

func buildResources(spec SimulationPodSpec) (corev1.ResourceRequirements, error) {
	cpuRequest := firstNonEmpty(spec.CPURequest, DefaultCPURequest)
	memoryRequest := firstNonEmpty(spec.MemoryRequest, DefaultMemoryRequest)
	cpuLimit := firstNonEmpty(spec.CPULimit, cpuRequest)
	memoryLimit := firstNonEmpty(spec.MemoryLimit, memoryRequest)

	requestCPU, err := resource.ParseQuantity(cpuRequest)
	if err != nil {
		return corev1.ResourceRequirements{}, err
	}
	requestMemory, err := resource.ParseQuantity(memoryRequest)
	if err != nil {
		return corev1.ResourceRequirements{}, err
	}
	limitCPU, err := resource.ParseQuantity(cpuLimit)
	if err != nil {
		return corev1.ResourceRequirements{}, err
	}
	limitMemory, err := resource.ParseQuantity(memoryLimit)
	if err != nil {
		return corev1.ResourceRequirements{}, err
	}

	return corev1.ResourceRequirements{
		Requests: corev1.ResourceList{
			corev1.ResourceCPU:    requestCPU,
			corev1.ResourceMemory: requestMemory,
		},
		Limits: corev1.ResourceList{
			corev1.ResourceCPU:    limitCPU,
			corev1.ResourceMemory: limitMemory,
		},
	}, nil
}

func int64Ptr(value int64) *int64 {
	return &value
}

func boolPtr(value bool) *bool {
	return &value
}

func quantityPtr(value string) *resource.Quantity {
	quantity := resource.MustParse(value)
	return &quantity
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if value != "" {
			return value
		}
	}
	return ""
}
