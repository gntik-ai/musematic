package code_bridge

import "testing"

func TestClientAddress(t *testing.T) {
	client := NewClient("sandbox-manager:50053")
	if client.Address() != "sandbox-manager:50053" {
		t.Fatalf("Address() = %s", client.Address())
	}

	var nilClient *Client
	if nilClient.Address() != "" {
		t.Fatalf("nil client address = %s, want empty", nilClient.Address())
	}
}
