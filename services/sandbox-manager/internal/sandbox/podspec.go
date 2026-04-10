package sandbox

import (
	"fmt"
	"time"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/templates"
	v1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

func BuildPodSpec(sandboxID string, tmpl templates.Definition, req *sandboxv1.CreateSandboxRequest, namespace string, maxTimeout time.Duration) (*v1.Pod, error) {
	limits := mergeResourceLimits(tmpl.Limits, req.GetResourceOverrides())
	resources, err := buildResources(limits)
	if err != nil {
		return nil, err
	}
	name := fmt.Sprintf("sandbox-%s", shortID(sandboxID))
	labels := map[string]string{
		"app":               "sandbox",
		"musematic/sandbox": "true",
		"sandbox_id":        sandboxID,
		"execution_id":      req.GetCorrelation().GetExecutionId(),
		"workspace_id":      req.GetCorrelation().GetWorkspaceId(),
		"managed-by":        "sandbox-manager",
	}
	dnsPolicy := v1.DNSNone
	dnsConfig := &v1.PodDNSConfig{}
	if req.GetNetworkEnabled() {
		dnsPolicy = v1.DNSClusterFirst
		dnsConfig = nil
		labels["musematic/network-allowed"] = "true"
	}
	activeDeadline := int64(maxTimeout.Seconds())
	envVars := make([]v1.EnvVar, 0, len(req.GetEnvVars()))
	for key, value := range req.GetEnvVars() {
		envVars = append(envVars, v1.EnvVar{Name: key, Value: value})
	}
	pod := &v1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      name,
			Namespace: namespace,
			Labels:    labels,
		},
		Spec: v1.PodSpec{
			AutomountServiceAccountToken: boolPtr(false),
			HostNetwork:                  false,
			HostPID:                      false,
			HostIPC:                      false,
			EnableServiceLinks:           boolPtr(false),
			RestartPolicy:                v1.RestartPolicyNever,
			DNSPolicy:                    dnsPolicy,
			DNSConfig:                    dnsConfig,
			ActiveDeadlineSeconds:        &activeDeadline,
			SecurityContext:              BuildPodSecurityContext(),
			Containers: []v1.Container{{
				Name:            "sandbox",
				Image:           tmpl.Image,
				ImagePullPolicy: v1.PullIfNotPresent,
				Command:         []string{"sleep", "infinity"},
				WorkingDir:      tmpl.WorkingDir,
				SecurityContext: BuildContainerSecurityContext(),
				Resources:       resources,
				Env:             envVars,
				VolumeMounts: []v1.VolumeMount{
					{Name: "tmp", MountPath: "/tmp"},
					{Name: "workspace", MountPath: "/workspace"},
					{Name: "output", MountPath: "/output"},
				},
			}},
			Volumes: []v1.Volume{
				{
					Name: "tmp",
					VolumeSource: v1.VolumeSource{
						EmptyDir: &v1.EmptyDirVolumeSource{SizeLimit: quantityPtr("256Mi")},
					},
				},
				{
					Name: "workspace",
					VolumeSource: v1.VolumeSource{
						EmptyDir: &v1.EmptyDirVolumeSource{SizeLimit: quantityPtr("512Mi")},
					},
				},
				{
					Name: "output",
					VolumeSource: v1.VolumeSource{
						EmptyDir: &v1.EmptyDirVolumeSource{SizeLimit: quantityPtr("128Mi")},
					},
				},
			},
		},
	}
	return pod, nil
}

func mergeResourceLimits(base *sandboxv1.ResourceLimits, override *sandboxv1.ResourceLimits) *sandboxv1.ResourceLimits {
	if base == nil {
		base = &sandboxv1.ResourceLimits{}
	}
	if override == nil {
		copy := *base
		return &copy
	}
	out := *base
	if override.CpuRequest != "" {
		out.CpuRequest = override.CpuRequest
	}
	if override.CpuLimit != "" {
		out.CpuLimit = override.CpuLimit
	}
	if override.MemoryRequest != "" {
		out.MemoryRequest = override.MemoryRequest
	}
	if override.MemoryLimit != "" {
		out.MemoryLimit = override.MemoryLimit
	}
	return &out
}

func buildResources(limits *sandboxv1.ResourceLimits) (v1.ResourceRequirements, error) {
	requests := v1.ResourceList{}
	resourceLimits := v1.ResourceList{}
	if limits.GetCpuRequest() != "" {
		requests[v1.ResourceCPU] = resource.MustParse(limits.GetCpuRequest())
	}
	if limits.GetMemoryRequest() != "" {
		requests[v1.ResourceMemory] = resource.MustParse(limits.GetMemoryRequest())
	}
	if limits.GetCpuLimit() != "" {
		resourceLimits[v1.ResourceCPU] = resource.MustParse(limits.GetCpuLimit())
	}
	if limits.GetMemoryLimit() != "" {
		resourceLimits[v1.ResourceMemory] = resource.MustParse(limits.GetMemoryLimit())
	}
	storage := resource.MustParse("1Gi")
	resourceLimits[v1.ResourceEphemeralStorage] = storage
	requests[v1.ResourceEphemeralStorage] = storage
	return v1.ResourceRequirements{
		Requests: requests,
		Limits:   resourceLimits,
	}, nil
}

func quantityPtr(value string) *resource.Quantity {
	q := resource.MustParse(value)
	return &q
}

func shortID(value string) string {
	if len(value) <= 8 {
		return value
	}
	return value[:8]
}
