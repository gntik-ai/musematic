package executor

import (
	"strings"
	"testing"

	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/templates"
)

func TestBuildCommandByTemplate(t *testing.T) {
	tests := []struct {
		name     string
		template templates.Definition
		code     string
		expect   string
	}{
		{name: "python", template: templates.PythonTemplate(), code: "print('ok')", expect: "python3"},
		{name: "node", template: templates.NodeTemplate(), code: "console.log('ok')", expect: "node"},
		{name: "go", template: templates.GolangTemplate(), code: "package main\nfunc main(){}", expect: "/workspace/main.go"},
		{name: "reasoning", template: templates.CodeAsReasoningTemplate(), code: "print(42)", expect: "json.dumps"},
	}
	for _, tt := range tests {
		command := BuildCommand(tt.template, tt.code, tt.template.TimeoutSeconds)
		if !strings.Contains(strings.Join(command, " "), tt.expect) {
			t.Fatalf("%s command missing %q: %v", tt.name, tt.expect, command)
		}
	}
}

func TestBuildCommandFallbacks(t *testing.T) {
	command := BuildCommand(templates.Definition{Name: "custom", TimeoutSeconds: 7}, "  echo ok  ", 0)
	if len(command) != 3 || command[0] != "sh" || command[1] != "-lc" || command[2] != "echo ok" {
		t.Fatalf("unexpected fallback command %v", command)
	}

	command = BuildCommand(templates.PythonTemplate(), "print('ok')", 0)
	if !strings.Contains(strings.Join(command, " "), " 30s ") {
		t.Fatalf("expected default timeout to be used, got %v", command)
	}
}
