package launcher

import (
	"fmt"
	"regexp"
	"strings"

	runtimev1 "github.com/andrea-mucci/musematic/services/runtime-controller/api/grpc/v1"
	v1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

var invalidLabelChars = regexp.MustCompile(`[^a-z0-9.-]+`)

func BuildPodSpec(contract *runtimev1.RuntimeContract, presignedURL string, namespace string, secretVolumes []v1.VolumeProjection, secretEnvs []v1.EnvVar) *v1.Pod {
	correlation := correlationContext(contract)
	executionID := correlation.ExecutionId
	workspaceID := correlation.WorkspaceId
	podName := buildPodName(executionID)

	envVars := []v1.EnvVar{
		{Name: "EXECUTION_ID", Value: executionID},
		{Name: "WORKSPACE_ID", Value: workspaceID},
	}
	for key, value := range contract.EnvVars {
		envVars = append(envVars, v1.EnvVar{Name: key, Value: value})
	}
	envVars = append(envVars, secretEnvs...)

	pod := &v1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      podName,
			Namespace: namespace,
			Labels: map[string]string{
				"app":          "agent-runtime",
				"execution_id": sanitizeLabelValue(executionID),
				"workspace_id": sanitizeLabelValue(workspaceID),
				"agent_fqn":    sanitizeLabelValue(contract.AgentRevision),
				"managed_by":   "runtime-controller",
			},
		},
		Spec: v1.PodSpec{
			RestartPolicy: v1.RestartPolicyNever,
			InitContainers: []v1.Container{
				{
					Name:    "package-downloader",
					Image:   "curlimages/curl:latest",
					Command: []string{"/bin/sh", "-c"},
					Args:    []string{fmt.Sprintf("curl -fsSL -o /agent-package/package.tar.gz %q && tar xzf /agent-package/package.tar.gz -C /agent-package/", presignedURL)},
					Env:     []v1.EnvVar{{Name: "AGENT_PACKAGE_URL", Value: presignedURL}},
					VolumeMounts: []v1.VolumeMount{
						{Name: "agent-package", MountPath: "/agent-package"},
					},
				},
			},
			Containers: []v1.Container{
				{
					Name:         "agent-runtime",
					Image:        "ghcr.io/andrea-mucci/musematic-agent-runtime:latest",
					Env:          envVars,
					Resources:    buildResourceRequirements(contract.ResourceLimits),
					VolumeMounts: buildVolumeMounts(secretVolumes),
				},
			},
			Volumes: []v1.Volume{
				{Name: "agent-package", VolumeSource: v1.VolumeSource{EmptyDir: &v1.EmptyDirVolumeSource{}}},
				{
					Name: "secrets-volume",
					VolumeSource: v1.VolumeSource{
						Projected: &v1.ProjectedVolumeSource{Sources: secretVolumes},
					},
				},
			},
		},
	}
	return pod
}

func sanitizeLabelValue(value string) string {
	value = strings.ToLower(value)
	value = invalidLabelChars.ReplaceAllString(value, "-")
	value = strings.Trim(value, "-.")
	if len(value) > 63 {
		value = value[:63]
	}
	if value == "" {
		return "unknown"
	}
	return value
}

func buildPodName(executionID string) string {
	short := strings.ReplaceAll(executionID, "-", "")
	if len(short) > 8 {
		short = short[:8]
	}
	if short == "" {
		short = "unknown"
	}
	return "runtime-" + short
}

func buildResourceRequirements(limits *runtimev1.ResourceLimits) v1.ResourceRequirements {
	if limits == nil {
		return v1.ResourceRequirements{}
	}
	requests := v1.ResourceList{}
	limitsList := v1.ResourceList{}
	if limits.CpuRequest != "" {
		requests[v1.ResourceCPU] = resource.MustParse(limits.CpuRequest)
	}
	if limits.MemoryRequest != "" {
		requests[v1.ResourceMemory] = resource.MustParse(limits.MemoryRequest)
	}
	if limits.CpuLimit != "" {
		limitsList[v1.ResourceCPU] = resource.MustParse(limits.CpuLimit)
	}
	if limits.MemoryLimit != "" {
		limitsList[v1.ResourceMemory] = resource.MustParse(limits.MemoryLimit)
	}
	return v1.ResourceRequirements{Requests: requests, Limits: limitsList}
}

func buildVolumeMounts(secretVolumes []v1.VolumeProjection) []v1.VolumeMount {
	mounts := []v1.VolumeMount{{Name: "agent-package", MountPath: "/agent", ReadOnly: true}}
	if len(secretVolumes) > 0 {
		mounts = append(mounts, v1.VolumeMount{Name: "secrets-volume", MountPath: "/run/secrets", ReadOnly: true})
	}
	return mounts
}

func correlationContext(r *runtimev1.RuntimeContract) *runtimev1.CorrelationContext {
	if r == nil || r.CorrelationContext == nil {
		return &runtimev1.CorrelationContext{}
	}
	return r.CorrelationContext
}
