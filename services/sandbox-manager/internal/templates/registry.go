package templates

import (
	"fmt"
	"sort"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
)

type Definition struct {
	Name           string
	Image          string
	Limits         *sandboxv1.ResourceLimits
	TimeoutSeconds int32
	WorkingDir     string
	Runtime        string
}

var builtins = map[string]Definition{
	"python3.12":        PythonTemplate(),
	"node20":            NodeTemplate(),
	"go1.22":            GolangTemplate(),
	"code-as-reasoning": CodeAsReasoningTemplate(),
}

func Lookup(name string) (Definition, error) {
	template, ok := builtins[name]
	if !ok {
		return Definition{}, fmt.Errorf("unknown sandbox template %q", name)
	}
	return template, nil
}

func Names() []string {
	names := make([]string, 0, len(builtins))
	for name := range builtins {
		names = append(names, name)
	}
	sort.Strings(names)
	return names
}
