#!/nix/store/0nxvi9r5ymdlr2p24rjj9qzyms72zld1-bash-interactive-5.2p37/bin/bash
# Local build and push script for registry.rptr.dev

set -e

REGISTRY="registry.rptr.dev"
IMAGE_NAME="synth-bot"
TAG="cyberpunk"
GIT_SHA=$(git rev-parse --short HEAD)
BRANCH=$(git rev-parse --abbrev-ref HEAD)

echo "🔨 Building Docker image..."
docker build -t ${REGISTRY}/${IMAGE_NAME}:${TAG} .

echo "🏷️  Tagging image..."
docker tag ${REGISTRY}/${IMAGE_NAME}:${TAG} ${REGISTRY}/${IMAGE_NAME}:${BRANCH}-${GIT_SHA}

echo "🔐 Logging into registry..."
docker login ${REGISTRY}

echo "📤 Pushing images..."
docker push ${REGISTRY}/${IMAGE_NAME}:${TAG}
docker push ${REGISTRY}/${IMAGE_NAME}:${BRANCH}-${GIT_SHA}

echo "✅ Successfully pushed:"
echo "  - ${REGISTRY}/${IMAGE_NAME}:${TAG}"
echo "  - ${REGISTRY}/${IMAGE_NAME}:${BRANCH}-${GIT_SHA}"
