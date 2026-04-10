package templates

import (
	"fmt"
	"strings"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
)

func CodeAsReasoningTemplate() Definition {
	return Definition{
		Name:  "code-as-reasoning",
		Image: "python:3.12-slim",
		Limits: &sandboxv1.ResourceLimits{
			CpuRequest:    "100m",
			CpuLimit:      "250m",
			MemoryRequest: "128Mi",
			MemoryLimit:   "128Mi",
		},
		TimeoutSeconds: 15,
		WorkingDir:     "/workspace",
		Runtime:        "code-as-reasoning",
	}
}

func BuildWrappedCommand(code string, timeoutSeconds int32) []string {
	if timeoutSeconds <= 0 {
		timeoutSeconds = CodeAsReasoningTemplate().TimeoutSeconds
	}
	quoted := strings.ReplaceAll(code, `"""`, `\"\"\"`)
	script := fmt.Sprintf(`
import io, json, contextlib
stdout_buffer = io.StringIO()
stderr_buffer = io.StringIO()
scope = {}
exit_code = 0
with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
    try:
        exec("""%s""", scope, scope)
    except Exception as exc:
        print(exc, file=stderr_buffer)
        exit_code = 1
print(json.dumps({"result": stdout_buffer.getvalue(), "error": stderr_buffer.getvalue(), "exit_code": exit_code}))
`, quoted)
	return []string{"timeout", "--kill-after=2s", fmt.Sprintf("%ds", timeoutSeconds), "python3", "-c", script}
}
