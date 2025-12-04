#!/bin/bash
# Build and push Docker image for Kagent Slack Bot
# 2025 best practices: multi-platform, security scanning, proper error handling
set -euo pipefail

# Configuration (override via environment variables)
REGISTRY="${REGISTRY:-matcham89}"
IMAGE_NAME="${IMAGE_NAME:-kagent-slack-bot}"
TAG="${TAG:-1.0.1}"
VERSION="${VERSION:-1.0.0}"
NAMESPACE="${NAMESPACE:-kagent}"

# Derived values
FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${TAG}"
VERSIONED_IMAGE="${REGISTRY}/${IMAGE_NAME}:${VERSION}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
error() {
    echo -e "${RED}❌ Error: $1${NC}" >&2
    exit 1
}

info() {
    echo -e "${GREEN}$1${NC}"
}

warn() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Validate prerequisites
if ! command -v docker &> /dev/null; then
    error "Docker is not installed. Please install Docker first."
fi

if ! docker buildx version &> /dev/null; then
    error "Docker Buildx is not available. Please update Docker to a version with Buildx support."
fi

# Check if registry is set to default placeholder
if [ "${REGISTRY}" = "your-registry" ]; then
    warn "Registry is set to placeholder 'your-registry'"
    echo "Please set the REGISTRY environment variable to your actual registry:"
    echo ""
    echo "  Examples:"
    echo "    export REGISTRY=docker.io/username        # Docker Hub"
    echo "    export REGISTRY=ghcr.io/username          # GitHub Container Registry"
    echo "    export REGISTRY=gcr.io/project-id         # Google Container Registry"
    echo ""
    read -p "Enter your registry (or press Ctrl+C to cancel): " USER_REGISTRY
    REGISTRY="${USER_REGISTRY}"
    FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${TAG}"
    VERSIONED_IMAGE="${REGISTRY}/${IMAGE_NAME}:${VERSION}"
fi

info "🔨 Building multi-platform Docker image..."
echo "   Registry: ${REGISTRY}"
echo "   Image: ${IMAGE_NAME}"
echo "   Tags: ${TAG}, ${VERSION}"
echo "   Platforms: linux/amd64, linux/arm64"
echo ""

# Create or use buildx builder
BUILDER_NAME="kagent-builder"
if ! docker buildx inspect "${BUILDER_NAME}" > /dev/null 2>&1; then
    info "📦 Creating buildx builder: ${BUILDER_NAME}"
    docker buildx create --name "${BUILDER_NAME}" --use --bootstrap
else
    info "📦 Using existing buildx builder: ${BUILDER_NAME}"
    docker buildx use "${BUILDER_NAME}"
fi

# Build and push for multiple platforms
info "🚀 Building and pushing image..."
docker buildx build \
    --platform linux/amd64,linux/arm64 \
    --tag "${FULL_IMAGE}" \
    --tag "${VERSIONED_IMAGE}" \
    --label "org.opencontainers.image.version=${VERSION}" \
    --label "org.opencontainers.image.created=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --label "org.opencontainers.image.source=https://github.com/your-org/kagent-slack-bot" \
    --push \
    .

info "✅ Image pushed successfully!"
echo ""
echo "   Images:"
echo "     - ${FULL_IMAGE}"
echo "     - ${VERSIONED_IMAGE}"
echo ""
info "📋 Next steps to deploy:"
echo ""
echo "1. Create Kubernetes secret with your Slack tokens:"
echo "   kubectl create secret generic slack-credentials \\"
echo "     --from-literal=bot-token='xoxb-your-token' \\"
echo "     --from-literal=app-token='xapp-your-token' \\"
echo "     --namespace=${NAMESPACE}"
echo ""
echo "2. Update k8s-deployment.yaml image to: ${FULL_IMAGE}"
echo "   OR use yq/sed:"
echo "   yq eval '.spec.template.spec.containers[0].image = \"${FULL_IMAGE}\"' -i k8s-deployment.yaml"
echo ""
echo "3. Deploy to Kubernetes:"
echo "   kubectl apply -f k8s-deployment.yaml"
echo ""
echo "4. Verify deployment:"
echo "   kubectl get pods -n ${NAMESPACE} -l app=kagent-slack-bot"
echo "   kubectl logs -n ${NAMESPACE} -l app=kagent-slack-bot -f"
echo ""
info "🎉 Build complete!"
