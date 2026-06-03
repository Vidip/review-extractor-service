#!/usr/bin/env bash
# Build and push the Gradio chat UI image to AWS ECR.
#
# Usage (from repo root):
#   ./scripts/push-ecr-gradio.sh
#   IMAGE_TAG=v1.2.3 ./scripts/push-ecr-gradio.sh
#
# Requires: aws CLI, docker, and ECR push permissions.

set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REGISTRY="767436615187.dkr.ecr.us-east-1.amazonaws.com/product-reviews-chat"
ECR_REPO_URI="767436615187.dkr.ecr.us-east-1.amazonaws.com/product-reviews-chat"
IMAGE_TAG="${IMAGE_TAG:-latest}"
IMAGE_NAME="${IMAGE_NAME:-product-reviews-chat}"
DOCKERFILE="${DOCKERFILE:-Dockerfile.gradio}"
DOCKER_PLATFORM="${DOCKER_PLATFORM:-linux/amd64}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "Region:     $AWS_REGION"
echo "Repository: $ECR_REPO_URI"
echo "Tag:        $IMAGE_TAG"
echo "Dockerfile: $DOCKERFILE"
if [[ -n "$DOCKER_PLATFORM" ]]; then
  echo "Platform:   $DOCKER_PLATFORM"
fi

aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY"

if [[ -n "$DOCKER_PLATFORM" ]]; then
  docker buildx create --use --name ecrbuilder >/dev/null 2>&1 || true
  docker buildx build \
    --platform "$DOCKER_PLATFORM" \
    -f "$DOCKERFILE" \
    -t "${IMAGE_NAME}:${IMAGE_TAG}" \
    --load \
    .
else
  docker build -f "$DOCKERFILE" -t "${IMAGE_NAME}:${IMAGE_TAG}" .
fi

docker tag "${IMAGE_NAME}:${IMAGE_TAG}" "${ECR_REPO_URI}:${IMAGE_TAG}"
docker push "${ECR_REPO_URI}:${IMAGE_TAG}"

echo "Pushed ${ECR_REPO_URI}:${IMAGE_TAG}"
