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