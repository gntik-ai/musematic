package sandbox

import (
	v1 "k8s.io/api/core/v1"
)

func BuildPodSecurityContext() *v1.PodSecurityContext {
	user := int64(65534)
	group := int64(65534)
	return &v1.PodSecurityContext{
		RunAsNonRoot: boolPtr(true),
		RunAsUser:    &user,
		RunAsGroup:   &group,
		FSGroup:      &group,
		SeccompProfile: &v1.SeccompProfile{
			Type: v1.SeccompProfileTypeRuntimeDefault,
		},
	}
}

func BuildContainerSecurityContext() *v1.SecurityContext {
	return &v1.SecurityContext{
		AllowPrivilegeEscalation: boolPtr(false),
		ReadOnlyRootFilesystem:   boolPtr(true),
		Capabilities: &v1.Capabilities{
			Drop: []v1.Capability{"ALL"},
		},
	}
}

func boolPtr(value bool) *bool {
	return &value
}
