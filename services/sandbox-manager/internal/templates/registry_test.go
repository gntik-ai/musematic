package templates

import (
	"strings"
	"testing"
)

func TestLookupBuiltins(t *testing.T) {
	names := []string{"python3.12", "node20", "go1.22", "code-as-reasoning"}
	for _, name := range names {
		template, err := Lookup(name)
		if err != nil {
			t.Fatalf("lookup %s: %v", name, err)
		}
		if template.Name != name {
			t.Fatalf("expected template %s, got %s", name, template.Name)
		}
	}
}

func TestLookupUnknownTemplate(t *testing.T) {
	if _, err := Lookup("unknown"); err == nil {
		t.Fatal("expected error for unknown template")
	}
}

func TestCodeAsReasoningCommandWrapsJSON(t *testing.T) {
	command := BuildWrappedCommand("result = 6 * 7\nprint(result)", 15)
	if len(command) < 6 {
		t.Fatalf("unexpected command length: %d", len(command))
	}
	if command[0] != "timeout" || command[3] != "python3" {
		t.Fatalf("unexpected wrapper command: %v", command)
	}
	if !strings.Contains(command[5], "json.dumps") {
		t.Fatalf("expected json wrapper, got %q", command[5])
	}
}
