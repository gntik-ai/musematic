package templates

import sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"

func GolangTemplate() Definition {
	return Definition{
		Name:  "go1.22",
		Image: "golang:1.22-alpine",
		Limits: &sandboxv1.ResourceLimits{
			CpuRequest:    "250m",
			CpuLimit:      "1000m",
			MemoryRequest: "256Mi",
			MemoryLimit:   "512Mi",
		},
		TimeoutSeconds: 45,
		WorkingDir:     "/workspace",
		Runtime:        "golang",
	}
}
