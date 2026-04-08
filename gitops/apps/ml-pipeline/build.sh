#!/bin/bash
set -e

# ============================================================================
# ML Pipeline Docker Image Builder
# ============================================================================
# Builds and pushes all custom Docker images needed by the ML pipeline.
# Run this on a machine with Docker before running deploy.sh.

#
# Usage:
#   ./build.sh               # Build and push all images
#   ./build.sh mlflow        # Build only the mlflow image
#   ./build.sh spark jupyter # Build spark and jupyter images
#   ./build.sh --no-push     # Build locally without pushing
#   ./build.sh --dry-run     # Show what would be built
#   ./build.sh --help        # Show this help message
#
# Valid image names: mlflow, feast, spark, jupyter.

# ============================================================================
# Configuration
# ============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

REGISTRY="${REGISTRY:-wearables42}"
TAG="${TAG:-v1.0.1}"
MLFLOW_IMAGE="${REGISTRY}/mlflow:latest"
FEAST_IMAGE="${REGISTRY}/feast:latest"
SPARK_IMAGE="${REGISTRY}/streaming-ml-pipeline:latest"
JUPYTER_IMAGE="${REGISTRY}/spark-notebook:latest"

PUSH_IMAGES="${PUSH_IMAGES:-true}"
DRY_RUN=false

# ============================================================================
# Helper Functions
# ============================================================================

log() {
    echo "🔨 $@"
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

build_and_push_image() {
    local dockerfile=$1
    local image=$2
    local context=${3:-.}

    log_substep "Building: $image"

    if [ "$DRY_RUN" = true ]; then
        echo "[DRY-RUN] DOCKER_BUILDKIT=1 docker build -f $dockerfile -t $image $context"
    else
        DOCKER_BUILDKIT=1 docker build -f "$dockerfile" -t "$image" "$context" || die "Failed to build $image"
    fi

    if [ "$PUSH_IMAGES" = true ]; then
        log_substep "Pushing: $image"
        if [ "$DRY_RUN" = false ]; then
            docker push "$image" || die "Failed to push $image"
        else
            echo "[DRY-RUN] docker push $image"
        fi
    fi
}

check_prerequisites() {
    log_step "Checking Prerequisites"

    for cmd in docker; do
        if ! command -v "$cmd" &> /dev/null; then
            die "Missing required tool: $cmd"
        else
            log_substep "✓ $cmd installed"
        fi
    done

    log_substep "Checking Docker daemon..."
    if ! docker ps &> /dev/null; then
        die "Cannot connect to Docker daemon"
    fi
    log_success "Docker daemon is running"
}

show_help() {
    cat << EOF
Usage: $0 [IMAGE...] [OPTIONS]

Builds and pushes custom Docker images for the ML pipeline.
Run this before deploy.sh on machines without Docker.

Images:
  mlflow        ${REGISTRY}/mlflow:latest               (mlflow/Dockerfile)
  feast         ${REGISTRY}/feast:latest                (feast/Dockerfile)
  spark         ${REGISTRY}/streaming-ml-pipeline:latest (spark_jobs/Dockerfile)
  jupyter       ${REGISTRY}/spark-notebook:latest       (ml-dev/Dockerfile)

  If no image names are given, all images are built.

Options:
  --no-push     Build images locally but don't push to registry
  --dry-run     Show what would be built without making changes
  -h, --help    Show this help message

Environment Variables:
  REGISTRY      Docker registry username/org (default: wearables42)
  TAG           Image tag (default: v1.0.1)
  PUSH_IMAGES   Push after building (default: true)

Examples:
  # Build and push all images
  ./build.sh

  # Build only the mlflow image
  ./build.sh mlflow

  # Build spark and jupyter without pushing
  ./build.sh spark jupyter --no-push

  # Use a different registry
  REGISTRY=myorg ./build.sh

EOF
}

# ============================================================================
# Main
# ============================================================================

build_image_by_name() {
    local name=$1
    case $name in
        mlflow)
            log_step "Building MLflow Image"
            build_and_push_image "mlflow/Dockerfile" "$MLFLOW_IMAGE" "."
            log_success "MLflow image ready: $MLFLOW_IMAGE"
            ;;
        feast)
            log_step "Building Feast Image"
            build_and_push_image "feast/Dockerfile" "$FEAST_IMAGE" "."
            log_success "Feast image ready: $FEAST_IMAGE"
            ;;
        spark)
            log_step "Building Spark Jobs Image"
            build_and_push_image "spark_jobs/Dockerfile" "$SPARK_IMAGE" "."
            log_success "Spark image ready: $SPARK_IMAGE"
            ;;
        jupyter)
            log_step "Building Jupyter Notebook Image"
            build_and_push_image "ml-dev/Dockerfile" "$JUPYTER_IMAGE" "."
            log_success "Jupyter notebook image ready: $JUPYTER_IMAGE"
            ;;
        *)
            die "Unknown image: $name. Valid names: mlflow, feast, spark, jupyter"
            ;;
    esac
}

main() {
    local selected_images=()

    while [[ $# -gt 0 ]]; do
        case $1 in
            --no-push)
                PUSH_IMAGES=false
                shift
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            mlflow|feast|spark|jupyter)
                selected_images+=("$1")
                shift
                ;;
            *)
                die "Unknown option: $1. Valid images: mlflow, feast, spark, jupyter"
                ;;
        esac
    done

    log "ML Pipeline Image Builder"
    log "========================="
    echo ""

    if [ "$DRY_RUN" = true ]; then
        log_warn "DRY-RUN MODE: No changes will be made"
    fi
    if [ "$PUSH_IMAGES" = false ]; then
        log_warn "PUSH disabled: images will be built locally only"
    fi

    check_prerequisites

    if [ ${#selected_images[@]} -gt 0 ]; then
        for image in "${selected_images[@]}"; do
            build_image_by_name "$image"
        done
    else
        build_image_by_name mlflow
        build_image_by_name feast
        build_image_by_name spark
        build_image_by_name jupyter
    fi

    echo ""
    log_success "Done. Run ./deploy.sh to deploy the stack."
}

main "$@"
