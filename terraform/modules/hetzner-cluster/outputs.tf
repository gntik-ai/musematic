output "load_balancer_ipv4" {
  description = "Ingress load balancer IPv4 address."
  value       = hcloud_load_balancer.ingress.ipv4
}

output "load_balancer_ipv6" {
  description = "Ingress load balancer IPv6 address."
  value       = hcloud_load_balancer.ingress.ipv6
}

output "control_plane_ipv4" {
  description = "Control-plane public IPv4 addresses."
  value       = hcloud_server.control_plane[*].ipv4_address
}

output "worker_ipv4" {
  description = "Worker public IPv4 addresses."
  value       = hcloud_server.worker[*].ipv4_address
}

output "kubeconfig_path" {
  description = "Suggested kubeconfig output path for the kubeadm bootstrap guide."
  value       = "${path.root}/kubeconfig"
}
