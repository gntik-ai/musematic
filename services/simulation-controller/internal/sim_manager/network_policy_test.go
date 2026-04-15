package sim_manager

import (
	"context"
	"errors"
	"testing"

	"github.com/stretchr/testify/require"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/client-go/kubernetes/fake"
	k8stesting "k8s.io/client-go/testing"
)

func TestBuildNetworkPolicyAndEnsureNetworkPolicy(t *testing.T) {
	client := fake.NewSimpleClientset()
	manager := NewPodManager(client, "sim-ns", "bucket-a", 30)

	policy := BuildNetworkPolicy("sim-ns")
	require.Equal(t, networkPolicyName, policy.Name)
	require.Equal(t, "sim-ns", policy.Namespace)
	require.Equal(t, "true", policy.Spec.PodSelector.MatchLabels[SimulationLabelKey])
	require.Len(t, policy.Spec.Egress, 2)
	require.EqualValues(t, 9000, policy.Spec.Egress[1].Ports[0].Port.IntVal)

	require.NoError(t, manager.EnsureNetworkPolicy(context.Background()))
	require.NoError(t, manager.EnsureNetworkPolicy(context.Background()))

	var nilManager *PodManager
	require.NoError(t, nilManager.EnsureNetworkPolicy(context.Background()))
	require.NoError(t, (&PodManager{}).EnsureNetworkPolicy(context.Background()))

	getErr := errors.New("get failed")
	errorClient := fake.NewSimpleClientset()
	errorClient.PrependReactor("get", "networkpolicies", func(k8stesting.Action) (bool, runtime.Object, error) {
		return true, nil, getErr
	})
	require.ErrorIs(t, NewPodManager(errorClient, "sim-ns", "bucket-a", 30).EnsureNetworkPolicy(context.Background()), getErr)
}
