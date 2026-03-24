#!/bin/bash

IMAGE_NAME="tomevox"
VERSION="${1:-}"

if [ -n "$VERSION" ]; then
  TAG="$VERSION"
  BUILD_ARGS="--build-arg APP_VERSION=$VERSION"
else
  TAG="latest"
fi
BASE_DIR=$(dirname "$0")
BUILD_TIMESTAMP=$(date +"%Y-%m-%d %H:%M%z")
BUILD_ARGS="--build-arg APP_BUILD_TIMESTAMP=$BUILD_TIMESTAMP"
echo "Building Docker image: ${IMAGE_NAME}:${TAG}"
docker buildx build --build-arg APP_BUILD_TIMESTAMP="$BUILD_TIMESTAMP" -t "${IMAGE_NAME}:${TAG}" -f "$BASE_DIR"/Dockerfile "$BASE_DIR"

echo ""
echo "Build complete!"
echo ""
echo "To run the container:"
echo "  docker run -p 5000:5000 ${IMAGE_NAME}:${TAG}"
echo ""
echo "Then open http://localhost:5000 in your browser."
