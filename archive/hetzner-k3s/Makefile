# =============================================================================
# K3s Cluster on Hetzner – Makefile
#
# Prerequisites: terraform, ansible-playbook, python3, kubectl, jq, openssl
#
# Quick start:
#   cp infra/terraform/terraform.tvars.example infra/terraform/terraform.tfvars
#   vim infra/terraform/terraform.tfvars   # add all HCLOUD_TOKEN + SSH keys 
#   make deploy
# =============================================================================

.PHONY: help deploy destroy tf-init tf-apply tf-destroy tf-output \
        inventory ansible status nodes clean gen-keys

SHELL    := /bin/bash
INFRA    := .
TF_DIR   := $(INFRA)/terraform
ANS_DIR  := $(INFRA)/ansible
INV_FILE := $(ANS_DIR)/inventory/hosts.yml

# ── Help ─────────────────────────────────────────────────────────────────────

help: 
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Full Pipeline ─────────────────────────────────────────────────────────────

deploy: tf-apply inventory ansible ## Full deployment: Hetzner -> K3s cluster
	@echo ""
	@echo "Cluster deployed."
	@echo "  Kubeconfig: $(INFRA)/kubeconfig.yaml"
	@echo "  Nodes:      make nodes"

destroy: tf-destroy ## Delete all Hetzner resources (terraform destroy)

# ── Terraform ─────────────────────────────────────────────────────────────────

tf-init: ## terraform init (do it once per project or after terraform changes)
	cd $(TF_DIR) && terraform init -upgrade

tf-apply: tf-init ## Provision server on Hetzner (terraform apply)
	@if [[ ! -f $(TF_DIR)/terraform.tfvars ]]; then \
	  echo "Error: $(TF_DIR)/terraform.tfvars not found."; \
	  echo "  Copy terraform.tvars.example -> terraform.tfvars and fill in HCLOUD_TOKEN."; \
	  exit 1; fi
	cd $(TF_DIR) && terraform apply -input=false -auto-approve

tf-destroy: ## Delete all Hetzner resources (terraform destroy)
	cd $(TF_DIR) && terraform destroy -input=false -auto-approve
	@rm -f $(INV_FILE) $(INFRA)/kubeconfig.yaml
	@echo "Done."

tf-output: ## Show Terraform-Outputs(IPs etc.)
	@cd $(TF_DIR) && terraform output

# ── Inventory ─────────────────────────────────────────────────────────────────

inventory: ## Generate Ansible inventory from Terraform output (runs after tf-apply)
	@mkdir -p $(ANS_DIR)/inventory
	@cd $(TF_DIR) && terraform output -json \
	  | python3 ../gen-inventory.py > ../ansible/inventory/hosts.yml
	@echo "Inventory written to $(INV_FILE):"
	@cat $(INV_FILE)

# ── Ansible ───────────────────────────────────────────────────────────────────

ansible: ## Run Ansible playbook (requires inventory to exist)
	@if [[ ! -f $(INV_FILE) ]]; then \
	  echo "Error: no inventory found. Run 'make inventory' first."; exit 1; fi
	cd $(ANS_DIR) && \
	  ANSIBLE_HOST_KEY_CHECKING=False \
	  ansible-playbook -i inventory/hosts.yml playbook.yml

ansible-master: ## Nur Master-Node einrichten
	@cd $(ANS_DIR) && \
	  ANSIBLE_HOST_KEY_CHECKING=False \
	  ansible-playbook -i inventory/hosts.yml playbook.yml --tags k3s,master

ansible-workers: ## Nur Worker-Nodes einrichten
	@cd $(ANS_DIR) && \
	  ANSIBLE_HOST_KEY_CHECKING=False \
	  ansible-playbook -i inventory/hosts.yml playbook.yml --tags k3s,worker

# ── Cluster-Status ────────────────────────────────────────────────────────────

nodes: ## Alle Cluster-Nodes anzeigen
	@KUBECONFIG=$(INFRA)/kubeconfig.yaml kubectl get nodes -o wide

status: ## Alle Pods im Cluster anzeigen
	@KUBECONFIG=$(INFRA)/kubeconfig.yaml kubectl get pods -A

# ── Utilities ─────────────────────────────────────────────────────────────────

clean: ## Remove generated files (inventory, kubeconfig)
	@rm -f $(INV_FILE) $(INFRA)/kubeconfig.yaml

gen-keys: ## Generate RSA key pair for Grafana JWT (written to secrets/)
	@mkdir -p secrets
	@openssl genpkey -algorithm RSA -out secrets/grafana-jwt-private.pem -pkeyopt rsa_keygen_bits:2048
	@openssl rsa -pubout -in secrets/grafana-jwt-private.pem -out secrets/grafana-jwt-public.pem
	@echo "Keys written to secrets/ (secrets/ is already in .gitignore)"
