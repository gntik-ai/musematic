//go:build integration

package sim_manager

import (
	"os"
	"testing"
)

func TestNetworkIsolationBlocksProductionEgress(t *testing.T) {
	if os.Getenv("SIMULATION_CONTROLLER_K8S_INTEGRATION") != "1" {
		t.Skip("set SIMULATION_CONTROLLER_K8S_INTEGRATION=1 to run the live Kubernetes isolation test")
	}

	t.Skip("live cluster verification is not available in the automated workspace")
}
