package artifacts

import "testing"

func TestBuildManifest(t *testing.T) {
	entries := BuildManifest("exec-1", "sandbox-1", []FileInfo{
		{Name: "result.txt", SizeBytes: 2},
		{Name: "./report.json", SizeBytes: 10},
	})
	if len(entries) != 2 {
		t.Fatalf("expected 2 manifest entries, got %d", len(entries))
	}
	if entries[0].ObjectKey != "sandbox-artifacts/exec-1/sandbox-1/result.txt" {
		t.Fatalf("unexpected object key %s", entries[0].ObjectKey)
	}
	if entries[1].ContentType != "application/json" {
		t.Fatalf("unexpected content type %s", entries[1].ContentType)
	}
}
