output "server_ip" {
  description = "Public IÜPV4 Address"
  value       = hcloud_server.server.ipv4_address
}

output "server_ipv6" {
  description = "IPv6 Adress "
  value       = hcloud_server.server.ipv6_address
}

output "server_id" {
  description = "Server ID"
  value       = hcloud_server.server.id
}