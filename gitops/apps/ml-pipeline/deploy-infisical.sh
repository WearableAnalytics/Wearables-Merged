#!/bin/bash
set -e

# ============================================================================
# Infisical Deployment Script
# ============================================================================
# Deploys the Infisical secret management server and operator.
# Run this BEFORE populating secrets (infisical/bootstrap.sh) and BEFORE
# running the main deploy.sh.
#
# Deployment order:
#   1. ./build.sh                     # Build custom container images
#   2. ./deploy-infisical.sh          # Deploy Infisical server + operator
#   3. ./infisical/bootstrap.sh       # Populate secrets into Infisical
#   4. ./deploy.sh                    # Deploy the rest of the ML pipeline
#
# Usage:
#   ./deploy-infisical.sh             # Deploy Infisical
#   ./deploy-infisical.sh --dry-run   # Show what would be deployed
#   ./deploy-infisical.sh --help      # Show this help message

# ============================================================================
# Configuration
# ============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

HELM_TIMEOUT="10m"
DRY_RUN=false

# ============================================================================
# Helper Functions
# ============================================================================

log() {
    echo "🚀 $@"
}

log_step() {
    echo ""
    echo "════════════════════════════════════════════════════════════════"
    echo "  $@"
    echo "════════════════════════════════════════════════════════════════"
}

log_substep() {
    echo "  → $@"
}

log_success() {
    echo "✅ $@"
}

log_warn() {
    echo "⚠️  $@"
}

log_error() {
    echo "❌ $@"
}

die() {
    log_error "$@"
    exit 1
}

run_command() {
    local description="$1"
    shift

    if [ "$DRY_RUN" = true ]; then
        echo "[DRY-RUN] $description" >&2
        echo "   Command: $@" >&2
    else
        log_substep "$description" >&2
        "$@" || die "Command failed: $@"
    fi
}

check_prerequisites() {
    log_step "Checking Prerequisites"

    local missing=()

    for cmd in kubectl helm openssl; do
        if ! command -v "$cmd" &> /dev/null; then
            missing+=("$cmd")
        else
            log_substep "✓ $cmd installed"
        fi
    done

    if [ ${#missing[@]} -gt 0 ]; then
        die "Missing required tools: ${missing[*]}"
    fi

    log_substep "Checking kubectl connectivity..."
    if ! kubectl cluster-info &> /dev/null; then
        die "Cannot connect to Kubernetes cluster"
    fi
    log_success "Connected to Kubernetes cluster"
}

show_help() {
    cat << EOF
Usage: $0 [OPTIONS]

Deploys the Infisical secret management server and Kubernetes operator.

This is step 2 of 4 in the full deployment sequence:
  1. ./build.sh                     Build custom container images
  2. ./deploy-infisical.sh          Deploy Infisical server + operator  <-- this script
  3. ./infisical/bootstrap.sh       Populate secrets into Infisical
  4. ./deploy.sh                    Deploy the rest of the ML pipeline

Options:
  --dry-run    Show what would be deployed without making changes
  -h, --help   Show this help message

After this script completes:
  - Port-forward to access the UI:
      kubectl port-forward svc/infisical-infisical-standalone-infisical -n infisical 8081:8080
  - Log in, create a project named 'ml-pipeline', create a Machine Identity,
    and export the token:
      export INFISICAL_TOKEN=<token>
  - Then run: ./infisical/bootstrap.sh
EOF
}

# ============================================================================
# Main
# ============================================================================

main() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dry-run) DRY_RUN=true; shift ;;
            -h|--help) show_help; exit 0 ;;
            *) die "Unknown option: $1" ;;
        esac
    done

    log "Infisical Deployment"
    log "===================="
    echo ""

    [ "$DRY_RUN" = true ] && log_warn "DRY-RUN MODE: No changes will be made"

    check_prerequisites

    log_step "Deploying Infisical Secret Management"

    run_command "Create infisical namespace" \
        bash -c "kubectl create namespace infisical --dry-run=client -o yaml | kubectl apply -f -"

    # Create the backend secret only if it doesn't already exist — regenerating
    # AUTH_SECRET or ENCRYPTION_KEY would break an existing installation.
    if [ "$DRY_RUN" = false ]; then
        if ! kubectl get secret infisical-secrets -n infisical &>/dev/null; then
            log_substep "Creating initial infisical-secrets..."
            kubectl create secret generic infisical-secrets \
                --namespace infisical \
                --from-literal=AUTH_SECRET="$(openssl rand -base64 32)" \
                --from-literal=ENCRYPTION_KEY="$(openssl rand -hex 16)" \
                --from-literal=SITE_URL="http://localhost" \
                --from-literal=DB_CONNECTION_URI="postgresql://infisical:root@postgresql:5432/infisicalDB" \
                --from-literal=REDIS_URL="redis://:mysecretpassword@redis-master:6379"
        else
            log_substep "infisical-secrets already exists — skipping creation."
        fi
    else
        echo "[DRY-RUN] Create secret: infisical-secrets (AUTH_SECRET, ENCRYPTION_KEY, ...)" >&2
    fi

    run_command "Add Infisical Helm repo" \
        helm repo add infisical-helm-charts https://dl.cloudsmith.io/public/infisical/helm-charts/helm/charts/

    run_command "Update Helm repos" \
        helm repo update

    run_command "Install Infisical server (standalone)" \
        helm upgrade --install infisical infisical-helm-charts/infisical-standalone \
            --namespace infisical \
            -f infisical/values.yaml \
            --timeout "$HELM_TIMEOUT" \
            --wait

    run_command "Install Infisical Secrets Operator" \
        helm upgrade --install infisical-secrets-operator infisical-helm-charts/secrets-operator \
            --namespace infisical \
            --timeout "$HELM_TIMEOUT" \
            --wait

    # Create target namespaces so the operator can sync secrets into them later
    for ns in prod-postgres ml-pipeline-seaweedfs ml-pipeline-lakefs ml-pipeline-mlflow ml-pipeline-feast ml-pipeline-spark-jobs ml-pipeline-kserve-models ml-pipeline-ml-dev; do
        run_command "Ensure namespace $ns exists" \
            bash -c "kubectl create namespace $ns --dry-run=client -o yaml | kubectl apply -f -"
    done

    log_success "Infisical deployed"
    echo ""
    echo "  Next steps:"
    echo "  1. Port-forward to access the UI:"
    echo "       kubectl port-forward svc/infisical-infisical-standalone-infisical -n infisical 8081:8080"
    echo "  2. Log in at http://localhost:8081, create project 'ml-pipeline',"
    echo "     create a Machine Identity, and copy the token."
    echo "  3. Populate secrets:"
    echo "       export INFISICAL_TOKEN=<token>"
    echo "       ./infisical/bootstrap.sh"
    echo "  4. Apply the operator auth secret and secret sync CRDs, then run the main deploy:"
    echo "       kubectl apply -f infisical/operator-auth-secret.yaml"
    echo "       kubectl apply -f infisical/secrets/"
    echo "       ./deploy.sh"
    echo ""
}

main "$@"
