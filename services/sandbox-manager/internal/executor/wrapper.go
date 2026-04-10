package executor

import (
	"fmt"
	"strings"

	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/templates"
)

func BuildCommand(template templates.Definition, code string, timeoutSeconds int32) []string {
	if timeoutSeconds <= 0 {
		timeoutSeconds = template.TimeoutSeconds
	}
	switch template.Name {
	case "python3.12":
		return []string{"timeout", "--kill-after=2s", fmt.Sprintf("%ds", timeoutSeconds), "python3", "-c", code}
	case "node20":
		return []string{"timeout", "--kill-after=2s", fmt.Sprintf("%ds", timeoutSeconds), "node", "-e", code}
	case "go1.22":
		script := fmt.Sprintf("cat > /workspace/main.go <<'EOF'\n%s\nEOF\nexec timeout --kill-after=2s %ds go run /workspace/main.go", code, timeoutSeconds)
		return []string{"sh", "-lc", script}
	case "code-as-reasoning":
		return templates.BuildWrappedCommand(code, timeoutSeconds)
	default:
		return []string{"sh", "-lc", strings.TrimSpace(code)}
	}
}
