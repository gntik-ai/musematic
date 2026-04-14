package templates

import (
	"strings"
	"testing"
)

func TestCodeAsReasoningTemplateDefaults(t *testing.T) {
	template := CodeAsReasoningTemplate()
	if template.Name != "code-as-reasoning" {
		t.Fatalf("unexpected template name %q", template.Name)
	}
	if template.Runtime != "code-as-reasoning" {
		t.Fatalf("unexpected runtime %q", template.Runtime)
	}
	if template.WorkingDir != "/workspace" {
		t.Fatalf("unexpected working dir %q", template.WorkingDir)
	}
	if template.TimeoutSeconds != 15 {
		t.Fatalf("unexpected timeout %d", template.TimeoutSeconds)
	}
}

func TestBuildWrappedCommandUsesPythonJSONWrapper(t *testing.T) {
	command := BuildWrappedCommand(`print("""hello""")`, 0)
	if len(command) != 6 {
		t.Fatalf("unexpected command length %d", len(command))
	}
	if command[0] != "timeout" || command[3] != "python3" {
		t.Fatalf("unexpected wrapped command %v", command)
	}
	if command[2] != "15s" {
		t.Fatalf("expected default timeout, got %s", command[2])
	}
	if !strings.Contains(command[5], "json.dumps") {
		t.Fatalf("expected JSON wrapper script, got %s", command[5])
	}
	if strings.Contains(command[5], `"""hello"""`) {
		t.Fatal("expected triple quotes to be escaped inside wrapper")
	}
}
