package templates

import sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"

func PythonTemplate() Definition {
	return Definition{
		Name:  "python3.12",
		Image: "python:3.12-slim",
		Limits: &sandboxv1.ResourceLimits{
			CpuRequest:    "100m",
			CpuLimit:      "500m",
			MemoryRequest: "128Mi",
			MemoryLimit:   "256Mi",
		},
		TimeoutSeconds: 30,
		WorkingDir:     "/workspace",
		Runtime:        "python",
	}
}
