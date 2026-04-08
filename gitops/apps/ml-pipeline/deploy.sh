#!/bin/bash
set -e

# ============================================================================
# ML Pipeline Deployment Script
# ============================================================================
# Deploys the ML pipeline stack (everything EXCEPT Infisical).
# Infisical must be deployed and seeded with secrets first.
#
# Full deployment order:
#   1. ./build.sh                     Build custom container images
#   2. ./deploy-infisical.sh          Deploy Infisical server + operator
#   3. ./infisical/bootstrap.sh       Populate secrets into Infisical
#   4. ./deploy.sh                    Deploy the rest of the ML pipeline  <-- this script
#
# Usage:
#   ./deploy.sh                     # Deploy everything
#   ./deploy.sh --dry-run           # Show what would be deployed
#   ./deploy.sh --start-from mlflow # Resume from a specific component
#   ./deploy.sh --help              # Show this help message

# ============================================================================
# Configuration
# ============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"


NAMESPACES=(
    ml-pipeline-argo
    ml-pipeline-seaweedfs
    ml-pipeline-lakefs
    ml-pipeline-mlflow
    ml-pipeline-feast
    ml-pipeline-spark-operator
    ml-pipeline-spark-jobs
    ml-pipeline-kserve-models
    ml-pipeline-ml-dev
)

# Helm configuration
HELM_TIMEOUT="10m"

# Flags
DRY_RUN=false
START_FROM=""
VERBOSE=false


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
        # Redirect dry-run info to stderr so it doesn't pollute pipes
        echo "[DRY-RUN] $description" >&2
        echo "   Command: $@" >&2
    else
        # Redirect log_substep to stderr
        log_substep "$description" >&2
        
        # Execute the command normally. 
        # Its stdout remains stdout, allowing pipes to work.
        "$@" || die "Command failed: $@"
    fi
}

wait_for_pod() {
    local namespace=$1
    local label=$2
    local timeout=${3:-300}

    log_substep "Waiting for pods in namespace '$namespace' with label '$label' (timeout: ${timeout}s)"
    kubectl wait --for=condition=ready pod \
        -l "$label" \
        -n "$namespace" \
        --timeout="${timeout}s" 2>/dev/null || log_warn "Pod wait timed out or no pods found"
}

should_run_step() {
    if [ -z "$START_FROM" ]; then
        return 0
    fi
    if [ "$START_FROM" = "$1" ]; then
        START_FROM=""  # Run this step and all following
        return 0
    fi
    return 1
}

check_prerequisites() {
    log_step "Checking Prerequisites"

    local missing=()

    # Check executables
    for cmd in kubectl helm; do
        if ! command -v "$cmd" &> /dev/null; then
            missing+=("$cmd")
        else
            log_substep "✓ $cmd installed"
        fi
    done

    if [ ${#missing[@]} -gt 0 ]; then
        die "Missing required tools: ${missing[*]}"
    fi

    # Check kubectl connectivity
    log_substep "Checking kubectl connectivity..."
    if ! kubectl cluster-info &> /dev/null; then
        die "Cannot connect to Kubernetes cluster"
    fi
    log_success "Connected to Kubernetes cluster"
}

# ============================================================================
# Deployment Steps
# ============================================================================

create_all_namespaces() {
    log_step "Creating Namespaces"

    for ns in "${NAMESPACES[@]}"; do
        run_command "Create namespace $ns" \
            kubectl create namespace "$ns" --dry-run=client -o yaml \
            | kubectl apply -f -
    done
}

sync_infisical_secrets() {
    should_run_step "infisical-secrets" || return 0

    log_step "Create Infisical secrets from local file"

    run_command "Sync secrets" \
        kubectl apply -f ./infisical/secrets
}

deploy_argo() {
    should_run_step "argo" || return 0

    log_step "Deploying Argo Workflows"

    run_command "Apply Argo kustomization" \
        kubectl apply -k argo/

    wait_for_pod "ml-pipeline-argo" "app=argo-server" 60
    log_success "Argo Workflows deployed"
}

deploy_postgres() {
    should_run_step "postgres" || return 0

    log_step "Setting Up PostgreSQL"

    # Ensure namespace exists
    run_command "Create prod-postgres namespace" \
        kubectl create namespace prod-postgres --dry-run=client -o yaml \
        | kubectl apply -f -

    run_command "Create PostgreSQL configmap" \
        kubectl apply -f SCRIPTS/postgres_setup/configmap.yaml

    run_command "Create PostgreSQL WorkflowTemplate" \
        kubectl apply -f SCRIPTS/postgres_setup/workflow-template.yaml

    run_command "Apply PostgreSQL workflow" \
        kubectl create -f SCRIPTS/postgres_setup/workflow.yaml -n prod-postgres --dry-run=client -o yaml \
        | kubectl create -f -

    log_substep "Waiting for PostgreSQL Workflow to complete..."
    if [ "$DRY_RUN" = false ]; then
        # Give Workflow time to start
        sleep 5
        kubectl wait --for=condition=Completed workflow \
            -l app=postgres-init \
            -n prod-postgres \
            --timeout=300s 2>/dev/null || log_warn "PostgreSQL Workflow completion check timed out"
    fi

    log_success "PostgreSQL setup complete"
}

deploy_seaweedfs() {
    should_run_step "seaweedfs" || return 0

    log_step "Deploying SeaweedFS"

    # Ensure namespace exists
    run_command "Create ml-pipeline-seaweedfs namespace" \
        kubectl create namespace ml-pipeline-seaweedfs --dry-run=client -o yaml \
        | kubectl apply -f -

    run_command "Build Helm dependencies" \
        bash -c "cd seaweedfs && helm dependency build ."

    run_command "Install SeaweedFS Helm chart" \
        helm upgrade --install seaweedfs seaweedfs \
            --namespace ml-pipeline-seaweedfs \
            --timeout "$HELM_TIMEOUT" \
            -f seaweedfs/values.yaml \
            --wait 2>/dev/null || log_warn "Helm wait timed out (SeaweedFS may still be deploying)"

    wait_for_pod "ml-pipeline-seaweedfs" "app.kubernetes.io/name=seaweedfs" 300
    log_success "SeaweedFS deployed"
}

setup_seaweedfs() {
    should_run_step "seaweedfs-setup" || return 0

    log_step "Setting Up SeaweedFS (S3 bucket, credentials)"

    run_command "Apply SeaweedFS WorkflowTemplate" \
        kubectl apply -f SCRIPTS/seaweedfs_setup/workflow-template.yaml -n ml-pipeline-seaweedfs

    run_command "Apply SeaweedFS setup (Workflow + Secret)" \
        kubectl apply -k SCRIPTS/seaweedfs_setup/

    log_substep "Waiting for SeaweedFS Workflow to complete..."
    if [ "$DRY_RUN" = false ]; then
        sleep 5
        kubectl wait --for=condition=Completed workflow \
            -l app=seaweedfs-setup \
            -n ml-pipeline-seaweedfs \
            --timeout=300s 2>/dev/null || log_warn "SeaweedFS Workflow completion check timed out"
    fi

    log_success "SeaweedFS setup complete"
}

deploy_lakefs() {
    should_run_step "lakefs" || return 0

    log_step "Deploying LakeFS"

    # Ensure namespace exists
    run_command "Create ml-pipeline-lakefs namespace" \
        kubectl create namespace ml-pipeline-lakefs --dry-run=client -o yaml \
        | kubectl apply -f -
    
    run_command "Add LakeFS Helm repo" \
        helm repo add lakefs https://charts.lakefs.io

    run_command "Build Helm dependencies" \
        bash -c "cd lakefs && helm dependency build ."

    run_command "Install LakeFS Helm chart" \
        helm upgrade --install lakefs lakefs \
            --namespace ml-pipeline-lakefs \
            --timeout "$HELM_TIMEOUT" \
            -f lakefs/values.yaml \
            --wait 2>/dev/null || log_warn "Helm wait timed out (LakeFS may still be deploying)"

    wait_for_pod "ml-pipeline-lakefs" "app.kubernetes.io/name=lakefs" 300
    log_success "LakeFS deployed"
}

setup_lakefs() {
    should_run_step "lakefs-setup" || return 0

    log_step "Setting Up LakeFS (repositories, branches)"

    run_command "Apply LakeFS setup" \
        kubectl create -f SCRIPTS/lakefs_setup/workflow.yaml -n ml-pipeline-lakefs --dry-run=client -o yaml \
        | kubectl create -f -

    
    log_substep "Waiting for LakeFS setup Workflow to complete..."
    if [ "$DRY_RUN" = false ]; then
        sleep 5
        kubectl wait --for=condition=Completed workflow \
            -l app=lakefs-setup \
            -n ml-pipeline-lakefs \
            --timeout=300s 2>/dev/null || log_warn "LakeFS setup Workflow completion check timed out"
    fi

    run_command "Create repos and branches" \
        kubectl create -f SCRIPTS/lakefs_setup/workflow-branch.yaml -n ml-pipeline-lakefs --dry-run=client -o yaml \
        | kubectl create -f -
    
    log_substep "Waiting for LakeFS branch setup Workflow to complete..."
    if [ "$DRY_RUN" = false ]; then
        sleep 5
        kubectl wait --for=condition=Completed workflow \
            -l app=lakefs-branch-setup \
            -n ml-pipeline-lakefs \
            --timeout=300s 2>/dev/null || log_warn "LakeFS branch setup Workflow completion check timed out"
    fi

    log_success "LakeFS setup complete"
}

deploy_mlflow() {
    should_run_step "mlflow" || return 0

    log_step "Deploying MLflow"

    # Ensure namespace exists
    run_command "Create ml-pipeline-mlflow namespace" \
        kubectl create namespace ml-pipeline-mlflow --dry-run=client -o yaml \
        | kubectl apply -f -

    run_command "Apply MLflow deployment (Kustomize)" \
        kubectl apply -k mlflow/

    wait_for_pod "ml-pipeline-mlflow" "app=mlflow-tracking" 300
    log_success "MLflow deployed"
}

deploy_feast() {
    should_run_step "feast" || return 0

    log_step "Deploying Feast"

    # Ensure namespace exists
    run_command "Create ml-pipeline-feast namespace" \
        kubectl create namespace ml-pipeline-feast --dry-run=client -o yaml \
        | kubectl apply -f -

    run_command "Apply Feast deployment (Kustomize)" \
        kubectl apply -k feast/

    wait_for_pod "ml-pipeline-feast" "app=feast-server" 300
    log_success "Feast deployed"
}

deploy_spark_operator() {
    should_run_step "spark-operator" || return 0

    log_step "Deploying Spark Operator"

    # Ensure namespaces exist
    run_command "Create ml-pipeline-spark-operator namespace" \
        kubectl create namespace ml-pipeline-spark-operator --dry-run=client -o yaml \
        | kubectl apply -f -

    run_command "Create ml-pipeline-spark-jobs namespace" \
        kubectl create namespace ml-pipeline-spark-jobs --dry-run=client -o yaml \
        | kubectl apply -f -

    run_command "Add Spark Operator Helm repo" \
        helm repo add spark-operator https://kubeflow.github.io/spark-operator

    run_command "Update Helm repos" \
        helm repo update

    run_command "Install Spark Operator Helm chart" \
        helm upgrade --install spark-operator spark-operator/spark-operator \
            --namespace ml-pipeline-spark-operator \
            --timeout "$HELM_TIMEOUT" \
            -f spark-operator/values.yaml \
            --wait 2>/dev/null || log_warn "Helm wait timed out (Spark Operator may still be deploying)"

    run_command "Apply Spark Operator RBAC (kustomize)" \
        kubectl apply -k spark-operator/

    log_substep "Restarting Spark Operator controller for RBAC to take effect..."
    if [ "$DRY_RUN" = false ]; then
        kubectl rollout restart deployment/spark-operator-controller -n ml-pipeline-spark-operator
        sleep 5
    else
        echo "[DRY-RUN] kubectl rollout restart deployment/spark-operator-controller -n ml-pipeline-spark-operator"
    fi

    wait_for_pod "ml-pipeline-spark-operator" "app.kubernetes.io/name=spark-operator" 300
    log_success "Spark Operator deployed"
}

deploy_spark_jobs() {
    should_run_step "spark-jobs" || return 0

    log_step "Deploying Spark Structured Streaming Jobs"

    run_command "Apply Spark Jobs (Kustomize)" \
        kubectl apply -k spark_jobs/

    log_substep "Waiting for SparkApplications to be submitted..."
    if [ "$DRY_RUN" = false ]; then
        sleep 5
        # Check status
        log_substep "Current SparkApplications status:"
        kubectl get sparkapplications -n ml-pipeline-spark-jobs || true
    fi

    log_success "Spark Jobs deployed"
}

deploy_ml_dev() {
    should_run_step "ml-dev" || return 0

    log_step "Deploying ML-Dev Jupyter Notebook (data scientist workspace)"

    run_command "Create ml-pipeline-ml-dev namespace" \
        kubectl create namespace ml-pipeline-ml-dev --dry-run=client -o yaml \
        | kubectl apply -f -

    run_command "Apply ml-dev resources (Kustomize)" \
        kubectl apply -k ml-dev/

    wait_for_pod "ml-pipeline-ml-dev" "app=spark-notebook" 120
    log_success "ML-Dev notebook deployed"
}

deploy_kserve() {
    should_run_step "kserve" || return 0

    log_step "Deploying KServe (v0.17.0) via OCI Registry"

    # 1. Install KServe CRDs
    # Note: CRDs are now bundled in 'kserve-crd'
    run_command "Install KServe CRDs" \
        helm upgrade --install kserve-crd oci://ghcr.io/kserve/charts/kserve-crd \
            --version v0.17.0 \
            --namespace kserve \
            --create-namespace \
            --timeout "$HELM_TIMEOUT" \
            --wait

    # 2. Wait for CRDs to be fully established in the API server before installing resources
    # (the kserve-resources chart itself contains a ClusterStorageContainer resource)
    if [ "$DRY_RUN" = false ]; then
        log_substep "Waiting for KServe CRDs to be established..."
        kubectl wait --for=condition=Established \
            crd/inferenceservices.serving.kserve.io \
            crd/clusterstoragecontainers.serving.kserve.io \
            --timeout=60s
    fi

    # 3. Install KServe Controller and Resources
    # IMPORTANT: The chart name changed from 'kserve' to 'kserve-resources' in v0.17.0
    run_command "Install KServe controller and resources" \
        helm upgrade --install kserve oci://ghcr.io/kserve/charts/kserve-resources \
            --version v0.17.0 \
            --namespace kserve \
            --create-namespace \
            --set kserve.controller.deploymentMode=RawDeployment \
            --timeout "$HELM_TIMEOUT" \
            --wait 2>/dev/null || log_warn "Helm wait timed out (KServe may still be starting)"

    # 4. Verify the controller pod
    wait_for_pod "kserve" "control-plane=kserve-controller-manager" 300

    # 5. Apply your local customizations
    run_command "Apply local KServe Kustomize overlays" \
        kubectl apply -k kserve/

    log_success "KServe v0.17.0 deployed successfully"
}

show_status() {
    log_step "Deployment Status Summary"

    local namespaces=("ml-pipeline-argo" "prod-postgres" "ml-pipeline-seaweedfs" "ml-pipeline-lakefs" "ml-pipeline-mlflow" "ml-pipeline-feast" "ml-pipeline-spark-operator" "ml-pipeline-spark-jobs" "ml-pipeline-ml-dev" "kserve" "ml-pipeline-kserve-models")

    for ns in "${namespaces[@]}"; do
        if kubectl get ns "$ns" &>/dev/null 2>&1; then
            log_substep "Namespace: $ns"
            kubectl get all -n "$ns" --no-headers 2>/dev/null | head -5 || echo "    (no resources)"
        fi
    done

    log_success "For detailed status, run:"
    echo "  kubectl get pods -A"
    echo "  kubectl get sparkapplications -n ml-pipeline-spark-jobs -w"
    echo ""
}

show_help() {
    cat << EOF
Usage: $0 [OPTIONS]

Deploys the ML pipeline stack to Kubernetes (everything except Infisical).
Infisical must already be deployed and seeded with secrets before running this.

Full deployment order:
  1. ./build.sh                     Build custom container images
  2. ./deploy-infisical.sh          Deploy Infisical server + operator
  3. ./infisical/bootstrap.sh       Populate secrets into Infisical
  4. ./deploy.sh                    Deploy the rest of the ML pipeline  <-- this script

Options:
  --dry-run              Show what would be deployed without making changes
  --start-from STEP      Resume deployment from a specific step
  -v, --verbose          Show more detailed output
  -h, --help             Show this help message

Steps (in order):
  postgres               PostgreSQL database setup
  seaweedfs              SeaweedFS S3-compatible storage
  seaweedfs-setup        SeaweedFS bucket and credential setup
  lakefs                 LakeFS versioned data lake
  lakefs-setup           LakeFS repository initialization
  mlflow                 MLflow model registry
  feast                  Feast feature store
  spark-operator         Spark Operator controller
  spark-jobs             Spark streaming pipeline jobs
  ml-dev                 ML-Dev Jupyter notebook (data scientist workspace)
  kserve                 KServe model inference service

Environment Variables:
  HELM_TIMEOUT           Helm operation timeout (default: 10m)

Examples:
  # Full first-time setup
  ./build.sh
  ./deploy-infisical.sh
  export INFISICAL_TOKEN=<token> && ./infisical/bootstrap.sh
  ./deploy.sh

  # Dry run
  ./deploy.sh --dry-run

  # Resume from a specific step
  ./deploy.sh --start-from spark-operator

EOF
}

# ============================================================================
# Main
# ============================================================================

main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --start-from)
                START_FROM="$2"
                shift 2
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                die "Unknown option: $1"
                ;;
        esac
    done

    log "ML Pipeline Unified Deployment"
    log "================================"
    echo ""

    if [ "$DRY_RUN" = true ]; then
        log_warn "DRY-RUN MODE: No changes will be made"
    fi

    if [ -n "$START_FROM" ]; then
        log_warn "Resuming from step: $START_FROM"
    fi

    # Run deployment steps
    check_prerequisites
    create_all_namespaces
    sync_infisical_secrets
    deploy_postgres
    deploy_seaweedfs
    setup_seaweedfs
    deploy_lakefs
    setup_lakefs
    deploy_mlflow
    deploy_feast
    deploy_spark_operator
    deploy_spark_jobs
    deploy_ml_dev
    deploy_kserve

    show_status

    log_success "Deployment complete!"
    echo ""
}

# Run main
main "$@"
