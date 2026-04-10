package sim_manager

import (
	"context"

	networkingv1 "k8s.io/api/networking/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/util/intstr"
)

const networkPolicyName = "simulation-deny-production-egress"

func (m *PodManager) EnsureNetworkPolicy(ctx context.Context) error {
	if m == nil || m.Client == nil {
		return nil
	}

	networkPolicies := m.Client.NetworkingV1().NetworkPolicies(m.Namespace)
	policy := BuildNetworkPolicy(m.Namespace)
	current, err := networkPolicies.Get(ctx, policy.Name, metav1.GetOptions{})
	if apierrors.IsNotFound(err) {
		_, createErr := networkPolicies.Create(ctx, policy, metav1.CreateOptions{})
		return createErr
	}
	if err != nil {
		return err
	}

	policy.ResourceVersion = current.ResourceVersion
	_, err = networkPolicies.Update(ctx, policy, metav1.UpdateOptions{})
	return err
}

func BuildNetworkPolicy(namespace string) *networkingv1.NetworkPolicy {
	return &networkingv1.NetworkPolicy{
		ObjectMeta: metav1.ObjectMeta{
			Name:      networkPolicyName,
			Namespace: namespace,
		},
		Spec: networkingv1.NetworkPolicySpec{
			PodSelector: metav1.LabelSelector{
				MatchLabels: map[string]string{SimulationLabelKey: "true"},
			},
			PolicyTypes: []networkingv1.PolicyType{networkingv1.PolicyTypeEgress},
			Egress: []networkingv1.NetworkPolicyEgressRule{
				{
					To: []networkingv1.NetworkPolicyPeer{{
						NamespaceSelector: &metav1.LabelSelector{
							MatchLabels: map[string]string{"kubernetes.io/metadata.name": namespace},
						},
					}},
				},
				{
					To: []networkingv1.NetworkPolicyPeer{{
						NamespaceSelector: &metav1.LabelSelector{
							MatchLabels: map[string]string{"kubernetes.io/metadata.name": "platform-data"},
						},
					}},
					Ports: []networkingv1.NetworkPolicyPort{
						{Port: intstrPtr(9000)},
						{Port: intstrPtr(9092)},
					},
				},
			},
		},
	}
}

func intstrPtr(value int32) *intstr.IntOrString {
	port := intstr.FromInt32(value)
	return &port
}
