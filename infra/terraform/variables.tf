variable "hcloud_token" {
  description = "Hetzner Cloud API Token"
  type        = string
  sensitive   = true
}

variable "server_name" {
  description = "Name des Servers"
  type        = string
  default     = "k3s-server"
}

variable "server_type" {
  description = "Server-Typ"
  type        = string
  default     = "cx21" # 2 vCPU, 4GB RAM
}

variable "location" {
  description = "Datacenter Location"
  type        = string
  default     = "nbg1" # Nürnberg
}

variable "users" {
  description = "User-Konfiguration"
  type = map(object({
    ssh_key = string
    sudo    = bool
  }))
}

variable "existing_ssh_key_names" {
  description = "Namen von bereits bei Hetzner hinterlegten SSH-Keys (optional)"
  type        = list(string)
  default     = []
}

variable "management_ips" {
  description = <<-EOT
    CIDR ranges allowed to reach management ports (SSH/22 and K3s API/6443).
    SECURITY: Restrict to known IP ranges before any production deployment with
    real patient data. Leaving this as 0.0.0.0/0 exposes the cluster control
    plane to the entire internet (findings F-11 and F-12).
    Example: ["203.0.113.10/32", "198.51.100.0/24"]
  EOT
  type    = list(string)
  # Default preserves current behaviour for the research deployment.
  # Override for production: -var='management_ips=["<your-ip>/32"]'
  default = ["0.0.0.0/0", "::/0"]
}