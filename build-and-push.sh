#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# POC Bible -- Build multi-arch Docker image and push to Docker Hub
# Usage: ./build-and-push.sh [tag]
# Default tag: latest
# Example: ./build-and-push.sh v1.0.0
# ──────────────────────────────────────────────────────────────────────────────
set -e

REPO="nixndme/poc-bible"
TAG="${1:-latest}"
IMAGE="${REPO}:${TAG}"

echo "Building and pushing: ${IMAGE}"
echo "Platforms: linux/amd64, linux/arm64"
echo ""

# Ensure buildx builder exists and supports multi-arch
if ! docker buildx inspect poc-bible-builder &>/dev/null; then
  echo "Creating buildx builder..."
  docker buildx create --name poc-bible-builder --use
fi
docker buildx use poc-bible-builder
docker buildx inspect --bootstrap

# Build and push
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t "${IMAGE}" \
  --push \
  .

# If tagging as a version, also push :latest
if [ "${TAG}" != "latest" ]; then
  docker buildx build \
    --platform linux/amd64,linux/arm64 \
    -t "${REPO}:latest" \
    --push \
    .
  echo ""
  echo "Also pushed: ${REPO}:latest"
fi

echo ""
echo "Done: ${IMAGE}"
echo ""
echo "Next: kubectl rollout restart deployment/poc-bible-app -n poc-bible"
