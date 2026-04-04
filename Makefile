# =============================================================================
# Wearables Platform – Makefile
#
# Prerequisites: terraform, ansible-playbook, helm, kubectl, jq, openssl
#
# Quick start:
#   cp infra/.env.example infra/.env
#   vim infra/.env        # fill in HCLOUD_TOKEN, SSH keys, domain, etc.
#   make deploy
# =============================================================================

.PHONY: help deploy destroy secrets helm-deploy status clean

SHELL := /bin/bash
SCRIPT_DIR := infra

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Full pipeline ─────────────────────────────────────────────────────────────

deploy: _check-env ## Full deployment: Hetzner → K3s → Helm (one-click)
	@chmod +x $(SCRIPT_DIR)/deploy.sh $(SCRIPT_DIR)/helm-deploy.sh
	@cd $(SCRIPT_DIR) && ./deploy.sh

destroy: _check-env ## Destroy all Hetzner infrastructure (terraform destroy)
	@chmod +x $(SCRIPT_DIR)/deploy.sh
	@cd $(SCRIPT_DIR) && ./deploy.sh --destroy

# ── Individual phases ─────────────────────────────────────────────────────────

tf-apply: _check-env ## Only run terraform apply (provision server)
	@source $(SCRIPT_DIR)/.env && \
	  cd $(SCRIPT_DIR)/terraform && \
	  terraform init -upgrade -input=false && \
	  terraform apply -input=false -auto-approve \
	    -var="hcloud_token=$$HCLOUD_TOKEN"

tf-output: ## Show Terraform outputs (server IP etc.)
	@cd $(SCRIPT_DIR)/terraform && terraform output

ansible: _check-env ## Only run Ansible playbook (requires server already provisioned)
	@source $(SCRIPT_DIR)/.env && \
	  cd $(SCRIPT_DIR)/ansible && \
	  ANSIBLE_HOST_KEY_CHECKING=False \
	  ansible-playbook -i inventory/hosts.yml playbook.yml

secrets: _check-env ## Bootstrap runtime secrets into the cluster
	@source $(SCRIPT_DIR)/.env && \
	  RESEARCHER_API_ACCESS_TOKEN=$$RESEARCHER_API_ACCESS_TOKEN \
	  BREVO_API_KEY=$$BREVO_API_KEY \
	  GRAFANA_JWT_PRIVATE_KEY_PATH=$$GRAFANA_JWT_PRIVATE_KEY_PATH \
	  scripts/bootstrap-runtime-secrets.sh

helm-deploy: _check-env ## Deploy all Helm charts (cluster must be running)
	@source $(SCRIPT_DIR)/.env && \
	  chmod +x $(SCRIPT_DIR)/helm-deploy.sh && \
	  $(SCRIPT_DIR)/helm-deploy.sh

helm-dry-run: ## Preview Helm deployment without applying
	@chmod +x $(SCRIPT_DIR)/helm-deploy.sh && \
	  $(SCRIPT_DIR)/helm-deploy.sh --dry-run

# ── Cluster status ────────────────────────────────────────────────────────────

status: ## Show cluster status (all pods + ingress routes)
	@echo "=== Pods ===" && kubectl get pods -A
	@echo "" && echo "=== IngressRoutes ===" && kubectl get ingressroute -A 2>/dev/null || kubectl get ingress -A

logs: ## Tail logs of a service (usage: make logs SVC=importservice)
	@kubectl logs -n wearables -l app=$(SVC) --tail=100 -f

# ── Utilities ─────────────────────────────────────────────────────────────────

clean: ## Remove generated files (inventory, tfvars, kubeconfig)
	@rm -f $(SCRIPT_DIR)/ansible/inventory/hosts.yml
	@rm -f $(SCRIPT_DIR)/terraform/terraform.tfvars
	@echo "Cleaned generated files (kubeconfig at ~/.kube/wearables not removed)"

gen-keys: ## Generate Grafana JWT key pair in secrets/
	@mkdir -p secrets
	@openssl genpkey -algorithm RSA -out secrets/grafana-jwt-private.pem -pkeyopt rsa_keygen_bits:2048
	@openssl rsa -pubout -in secrets/grafana-jwt-private.pem -out secrets/grafana-jwt-public.pem
	@echo "Keys generated in secrets/ – make sure secrets/ is in .gitignore!"

_check-env:
	@if [[ ! -f $(SCRIPT_DIR)/.env ]]; then \
	  echo "Error: infra/.env not found. Copy infra/.env.example to infra/.env"; exit 1; fi
