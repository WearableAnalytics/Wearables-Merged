# Public IPv4 address – used by gen-inventory.py to build the Ansible inventory
output "server_ip" {
  description = "Public IPv4 address of the K3s server"
  value       = hcloud_server.server.ipv4_address
}

# Public IPv6 address – available but not used by Ansible by default
output "server_ipv6" {
  description = "Public IPv6 address of the K3s server"
  value       = hcloud_server.server.ipv6_address
}

# Hetzner internal server ID – useful for debugging or referencing the resource via API
output "server_id" {
  description = "Hetzner Cloud server ID"
  value       = hcloud_server.server.id
}
