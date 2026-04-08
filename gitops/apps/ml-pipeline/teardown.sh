#!/bin/bash
set -e

# ============================================================================
# ML Pipeline Teardown Script
# ============================================================================
# Removes everything created by deploy.sh (reverse order).
# Does NOT remove Infisical — use teardown-infisical.sh for that.
#
# Usage:
#   ./teardown.sh              # Remove everything
#   ./teardown.sh --dry-run    # Show what would be removed
#   ./teardown.sh --help       # Show this help message

# ============================================================================
# Configuration
# ============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DRY_RUN=false

NAMESPACES=(
    ml-pipeline-kserve-models
    ml-pipeline-spark-jobs
    ml-pipeline-spark-operator
    ml-pipeline-feast
    ml-pipeline-mlflow
    ml-pipeline-lakefs
    ml-pipeline-seaweedfs
)

# ============================================================================
# Helper Functions
# ============================================================================

log_step() {
    echo ""
    echo "════════════════════════════════════════════════════════════════"
    echo "  $@"
    echo "════════════════════════════════════════════════════════════════"
}

log_substep() { echo "  → $@"; }
log_success()  { echo "✅ $@"; }
log_warn()     { echo "⚠️  $@"; }
log_error()    { echo "❌ $@"; }

run() {
    local description="$1"; shift
    if [ "$DRY_RUN" = true ]; then
        echo "[DRY-RUN] $description"
        echo "   Command: $*"
    else
        log_substep "$description"
        "$@" || log_warn "Command failed (continuing): $*"
    fi
}

show_help() {
    cat << EOF
Usage: $0 [OPTIONS]

Removes everything created by deploy.sh (Helm releases, namespaces, and
cluster-scoped resources). Does NOT touch Infisical.

Options:
  --dry-run    Show what would be removed without making changes
  -h, --help   Show this help message
EOF
}

# ============================================================================
# Teardown Steps (reverse deploy order)
# ============================================================================

teardown_prod_postgres_setup() {
    log_step "Removing everything created by prod-postgres-setup workflow"

    run "Delete prod-postgres-setup Argo Workflow artifacts" \
       kubectl create -f SCRIPTS/teardown/teardown-postgres_setup-workflow.yaml
}

teardown_kserve() {
    log_step "Removing KServe Resources"

    run "Delete ClusterStorageContainer mlflow-registry" \
        kubectl delete clusterstoragecontainer mlflow-registry --ignore-not-found
}

teardown_helm_releases() {
    log_step "Uninstalling Helm Releases"

    run "Uninstall spark-operator" \
        helm uninstall spark-operator --namespace ml-pipeline-spark-operator --ignore-not-found --wait

    run "Uninstall lakefs" \
        helm uninstall lakefs --namespace ml-pipeline-lakefs --ignore-not-found --wait

    run "Uninstall seaweedfs" \
        helm uninstall seaweedfs --namespace ml-pipeline-seaweedfs --ignore-not-found --wait
}

teardown_namespaces() {
    log_step "Deleting Namespaces"

    for ns in "${NAMESPACES[@]}"; do
        run "Delete namespace $ns" \
            kubectl delete namespace "$ns" --ignore-not-found --wait=false
    done

    if [ "$DRY_RUN" = false ]; then
        log_substep "Waiting for namespaces to terminate..."
        for ns in "${NAMESPACES[@]}"; do
            kubectl wait --for=delete namespace/"$ns" --timeout=120s 2>/dev/null \
                || log_warn "Namespace $ns did not terminate in time (may still be terminating)"
        done
    fi
}

# ============================================================================
# Main
# ============================================================================

main() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dry-run) DRY_RUN=true; shift ;;
            -h|--help) show_help; exit 0 ;;
            *) log_error "Unknown option: $1"; show_help; exit 1 ;;
        esac
    done

    echo "ML Pipeline Teardown"
    echo "===================="
    echo ""

    if [ "$DRY_RUN" = true ]; then
        log_warn "DRY-RUN MODE: No changes will be made"
        echo ""
    fi

    if ! kubectl cluster-info &>/dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi

    teardown_prod_postgres_setup
    teardown_kserve
    teardown_helm_releases
    teardown_namespaces

    log_success "Teardown complete"
    echo ""
}

main "$@"
