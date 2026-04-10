package templates

import sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"

func NodeTemplate() Definition {
	return Definition{
		Name:  "node20",
		Image: "node:20-slim",
		Limits: &sandboxv1.ResourceLimits{
			CpuRequest:    "100m",
			CpuLimit:      "500m",
			MemoryRequest: "128Mi",
			MemoryLimit:   "256Mi",
		},
		TimeoutSeconds: 30,
		WorkingDir:     "/workspace",
		Runtime:        "node",
	}
}
