#!/usr/bin/env bash
# =============================================================================
# deploy.sh – One-click deployment: Hetzner → K3s → Helm
#
# Usage:
#   cd infra/
#   cp .env.example .env && vim .env   # fill in your values
#   ./deploy.sh
#
# What this does:
#   1. terraform apply  → provisions Hetzner server
#   2. Generates Ansible inventory from Terraform output
#   3. Waits for SSH to be ready
#   4. ansible-playbook → hardens server, installs K3s
#   5. Fetches kubeconfig to ~/.kube/wearables
#   6. Runs bootstrap-runtime-secrets.sh (JWT, Grafana, BFF secrets)
#   7. Runs helm-deploy.sh (operators + all Helm charts in order)
#
# To destroy: ./deploy.sh --destroy
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TF_DIR="${SCRIPT_DIR}/terraform"
ANSIBLE_DIR="${SCRIPT_DIR}/ansible"
KUBECONFIG_PATH="${HOME}/.kube/wearables"

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}ℹ  $*${NC}"; }
success() { echo -e "${GREEN}✓  $*${NC}"; }
warn()    { echo -e "${YELLOW}⚠  $*${NC}"; }
error()   { echo -e "${RED}✗  $*${NC}" >&2; exit 1; }
step()    { echo -e "\n${BLUE}══ $* ══${NC}"; }

# ── Load .env ─────────────────────────────────────────────────────────────────
if [[ ! -f "${SCRIPT_DIR}/.env" ]]; then
  error "infra/.env not found. Copy infra/.env.example to infra/.env and fill in your values."
fi
# shellcheck disable=SC1091
set -a && source "${SCRIPT_DIR}/.env" && set +a

# ── Prerequisite check ────────────────────────────────────────────────────────
check_prereqs() {
  local missing=()
  for cmd in terraform ansible-playbook helm kubectl jq openssl ssh ssh-keyscan; do
    command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    error "Missing tools: ${missing[*]}\nInstall them before running deploy.sh"
  fi
  success "All prerequisites found"
}

# ── Destroy mode ──────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--destroy" ]]; then
  warn "Destroying all infrastructure..."
  cd "${TF_DIR}"
  terraform init -upgrade -input=false
  terraform destroy -var="hcloud_token=${HCLOUD_TOKEN}" -auto-approve
  success "Infrastructure destroyed"
  exit 0
fi

check_prereqs

# ── Phase 1: Terraform ────────────────────────────────────────────────────────
step "Phase 1: Provisioning Hetzner server with Terraform"

# Write tfvars from .env
SSH_PUBLIC_KEY="$(cat "${SSH_PUBLIC_KEY_PATH}")"

cat > "${TF_DIR}/terraform.tfvars" <<EOF
hcloud_token = "${HCLOUD_TOKEN}"
server_name  = "${TF_SERVER_NAME:-k3s-wearables}"
server_type  = "${TF_SERVER_TYPE:-cx31}"
location     = "${TF_LOCATION:-nbg1}"

users = {
  "${SSH_USER}" = {
    ssh_key = "${SSH_PUBLIC_KEY}"
    sudo    = true
  }
}
EOF

cd "${TF_DIR}"
terraform init -upgrade -input=false
terraform apply -input=false -auto-approve

SERVER_IP="$(terraform output -raw server_ip)"
success "Server provisioned: ${SERVER_IP}"

# ── Phase 2: Generate Ansible inventory ───────────────────────────────────────
step "Phase 2: Generating Ansible inventory"

cat > "${ANSIBLE_DIR}/inventory/hosts.yml" <<EOF
all:
  hosts:
    k3s_server:
      ansible_host: ${SERVER_IP}
      ansible_user: ${SSH_USER}
      ansible_become: yes
      ansible_become_method: sudo
      ansible_ssh_private_key_file: ${SSH_KEY_PATH}
  vars:
    ansible_python_interpreter: /usr/bin/python3
EOF

success "Inventory written for ${SERVER_IP}"

# ── Phase 3: Wait for SSH ─────────────────────────────────────────────────────
step "Phase 3: Waiting for SSH on ${SERVER_IP}"

MAX_WAIT=120
ELAPSED=0
until ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
    -i "${SSH_KEY_PATH}" \
    "root@${SERVER_IP}" "echo ok" >/dev/null 2>&1; do
  if [[ $ELAPSED -ge $MAX_WAIT ]]; then
    error "Timed out waiting for SSH after ${MAX_WAIT}s"
  fi
  info "  waiting... (${ELAPSED}s / ${MAX_WAIT}s)"
  sleep 5
  ELAPSED=$((ELAPSED + 5))
done

# Add to known_hosts
ssh-keyscan -H "${SERVER_IP}" >> "${HOME}/.ssh/known_hosts" 2>/dev/null

success "SSH is ready"

# ── Phase 4: Ansible ──────────────────────────────────────────────────────────
step "Phase 4: Running Ansible playbook (server hardening + K3s)"

cd "${ANSIBLE_DIR}"
ANSIBLE_HOST_KEY_CHECKING=False \
GRAFANA_ADMIN_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-$(openssl rand -base64 16)}" \
ansible-playbook \
  -i inventory/hosts.yml \
  playbook.yml \
  --extra-vars "grafana_admin_password=${GRAFANA_ADMIN_PASSWORD:-admin}"

success "Ansible playbook complete"

# ── Phase 5: Fetch kubeconfig ─────────────────────────────────────────────────
step "Phase 5: Fetching kubeconfig"

mkdir -p "$(dirname "${KUBECONFIG_PATH}")"
ssh -o StrictHostKeyChecking=no \
    -i "${SSH_KEY_PATH}" \
    "${SSH_USER}@${SERVER_IP}" \
    "sudo cat /etc/rancher/k3s/k3s.yaml" \
  | sed "s/127.0.0.1/${SERVER_IP}/g" \
  | sed "s/default/wearables/g" \
  > "${KUBECONFIG_PATH}"
chmod 600 "${KUBECONFIG_PATH}"

export KUBECONFIG="${KUBECONFIG_PATH}"
success "Kubeconfig saved to ${KUBECONFIG_PATH}"

# Verify cluster access
kubectl cluster-info >/dev/null 2>&1 || error "Cannot reach K8s API – check kubeconfig"
success "Cluster is reachable"

# ── Phase 6: Bootstrap runtime secrets ────────────────────────────────────────
step "Phase 6: Bootstrapping runtime secrets"

export KUBECONFIG="${KUBECONFIG_PATH}"

# Generate secrets if not provided
if [[ -z "${GRAFANA_ADMIN_PASSWORD:-}" ]]; then
  GRAFANA_ADMIN_PASSWORD="$(openssl rand -base64 16)"
  warn "Generated GRAFANA_ADMIN_PASSWORD (save this!): ${GRAFANA_ADMIN_PASSWORD}"
fi
if [[ -z "${POSTGRES_DEV_PASSWORD:-}" ]]; then
  POSTGRES_DEV_PASSWORD="$(openssl rand -base64 16)"
  warn "Generated POSTGRES_DEV_PASSWORD (save this!): ${POSTGRES_DEV_PASSWORD}"
fi
if [[ -z "${POSTGRES_PROD_PASSWORD:-}" ]]; then
  POSTGRES_PROD_PASSWORD="$(openssl rand -base64 16)"
  warn "Generated POSTGRES_PROD_PASSWORD (save this!): ${POSTGRES_PROD_PASSWORD}"
fi

export POSTGRES_DEV_PASSWORD POSTGRES_PROD_PASSWORD GRAFANA_ADMIN_PASSWORD

# Grafana JWT private key check
if [[ ! -f "${GRAFANA_JWT_PRIVATE_KEY_PATH:-}" ]]; then
  warn "Grafana JWT private key not found at ${GRAFANA_JWT_PRIVATE_KEY_PATH:-unset}"
  warn "Generating a new key pair in ./secrets/ ..."
  mkdir -p "${REPO_ROOT}/secrets"
  openssl genpkey -algorithm RSA -out "${REPO_ROOT}/secrets/grafana-jwt-private.pem" -pkeyopt rsa_keygen_bits:2048
  openssl rsa -pubout -in "${REPO_ROOT}/secrets/grafana-jwt-private.pem" \
    -out "${REPO_ROOT}/secrets/grafana-jwt-public.pem"
  GRAFANA_JWT_PRIVATE_KEY_PATH="${REPO_ROOT}/secrets/grafana-jwt-private.pem"
  warn "Keys generated in secrets/ – add secrets/*.pem to .gitignore!"
fi

RESEARCHER_API_ACCESS_TOKEN="${RESEARCHER_API_ACCESS_TOKEN:-}" \
BREVO_API_KEY="${BREVO_API_KEY:-}" \
SHARED_APP_JWT_SECRET="${SHARED_APP_JWT_SECRET:-}" \
GRAFANA_JWT_PRIVATE_KEY_PATH="${GRAFANA_JWT_PRIVATE_KEY_PATH}" \
  "${REPO_ROOT}/scripts/bootstrap-runtime-secrets.sh"

success "Runtime secrets applied"

# ── Phase 7: Helm deploy ──────────────────────────────────────────────────────
step "Phase 7: Deploying all Helm charts"

export KUBECONFIG="${KUBECONFIG_PATH}"
SHARED_APP_JWT_SECRET="${SHARED_APP_JWT_SECRET:-}" \
POSTGRES_DEV_PASSWORD="${POSTGRES_DEV_PASSWORD}" \
POSTGRES_PROD_PASSWORD="${POSTGRES_PROD_PASSWORD}" \
GRAFANA_ADMIN_PASSWORD="${GRAFANA_ADMIN_PASSWORD}" \
DOMAIN="${DOMAIN:-wearables.charite.de}" \
CERT_EMAIL="${CERT_EMAIL:-admin@charite.de}" \
  "${SCRIPT_DIR}/helm-deploy.sh"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ✅  Deployment complete                 ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""
echo "  Server IP:    ${SERVER_IP}"
echo "  Domain:       ${DOMAIN:-wearables.charite.de}"
echo "  Kubeconfig:   ${KUBECONFIG_PATH}"
echo ""
echo "  To use kubectl:"
echo "    export KUBECONFIG=${KUBECONFIG_PATH}"
echo "    kubectl get pods -A"
echo ""
echo "  To destroy:"
echo "    ./infra/deploy.sh --destroy"
