package sim_manager

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestBuildPodIncludesSimulationIsolationConfig(t *testing.T) {
	t.Parallel()

	pod, err := BuildPod(SimulationPodSpec{
		SimulationID:  "sim-123",
		AgentImage:    "busybox:latest",
		CPURequest:    "250m",
		MemoryRequest: "256Mi",
	}, DefaultNamespace, DefaultBucket, DefaultMaxDurationSec)
	require.NoError(t, err)

	require.Equal(t, "sim-sim-123", pod.Name)
	require.Equal(t, "true", pod.Labels[SimulationLabelKey])
	require.Equal(t, "sim-123", pod.Labels[SimulationIDLabelKey])
	require.Equal(t, "simulation-controller", pod.Annotations["simulation-created-by"])

	container := pod.Spec.Containers[0]
	env := map[string]string{}
	for _, variable := range container.Env {
		env[variable.Name] = variable.Value
	}
	require.Equal(t, "true", env["SIMULATION"])
	require.Equal(t, "sim-123", env["SIMULATION_ID"])
	require.Equal(t, DefaultBucket, env["SIMULATION_BUCKET"])
	require.Equal(t, "sim-123", env["SIMULATION_ARTIFACTS_PREFIX"])

	require.EqualValues(t, 65534, *pod.Spec.SecurityContext.RunAsUser)
	require.True(t, *pod.Spec.SecurityContext.RunAsNonRoot)
	require.EqualValues(t, 65534, *container.SecurityContext.RunAsUser)
	require.True(t, *container.SecurityContext.ReadOnlyRootFilesystem)
	require.Equal(t, []string{"ALL"}, []string{string(container.SecurityContext.Capabilities.Drop[0])})

	require.Len(t, pod.Spec.Volumes, 3)
	require.Equal(t, "512Mi", pod.Spec.Volumes[0].EmptyDir.SizeLimit.String())
	require.Equal(t, "1Gi", pod.Spec.Volumes[1].EmptyDir.SizeLimit.String())
	require.Equal(t, "256Mi", pod.Spec.Volumes[2].EmptyDir.SizeLimit.String())
}

func TestBuildPodAddsATEMounts(t *testing.T) {
	t.Parallel()

	pod, err := BuildPod(SimulationPodSpec{
		SimulationID:     "ate-sim",
		AgentImage:       "busybox:latest",
		ATEConfigMapName: "ate-session-1",
		ATESessionID:     "session-1",
	}, DefaultNamespace, DefaultBucket, DefaultMaxDurationSec)
	require.NoError(t, err)

	container := pod.Spec.Containers[0]
	env := map[string]string{}
	for _, variable := range container.Env {
		env[variable.Name] = variable.Value
	}
	require.Equal(t, "session-1", env["ATE_SESSION_ID"])
	require.Equal(t, "/ate/scenarios.json", env["ATE_SCENARIOS_PATH"])

	var foundMount bool
	for _, mount := range container.VolumeMounts {
		if mount.Name == "ate-config" && mount.MountPath == "/ate" && mount.ReadOnly {
			foundMount = true
		}
	}
	require.True(t, foundMount)
}
