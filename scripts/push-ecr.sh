#!/usr/bin/env bash
# Build and push the Docker image to AWS ECR.
#
# Usage (from repo root):
#   ./scripts/push-ecr.sh
#   IMAGE_TAG=v1.2.3 ./scripts/push-ecr.sh
#
# Requires: aws CLI, docker, and ECR push permissions.

set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REGISTRY="${ECR_REGISTRY:-${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com}"
ECR_REPO_URI="${ECR_REPO_URI:-${ECR_REGISTRY}/product-reviews}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
DOCKERFILE="${DOCKERFILE:-Dockerfile}"
# ECS Fargate/x86 tasks need linux/amd64 (set empty to use plain `docker build`).
DOCKER_PLATFORM="${DOCKER_PLATFORM:-linux/amd64}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "Region:    $AWS_REGION"
echo "Repository: $ECR_REPO_URI"
echo "Tag:       $IMAGE_TAG"
echo "Dockerfile: $DOCKERFILE"
if [[ -n "$DOCKER_PLATFORM" ]]; then
  echo "Platform:  $DOCKER_PLATFORM"
fi

aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY"

if [[ -n "$DOCKER_PLATFORM" ]]; then
  docker buildx create --use --name ecrbuilder >/dev/null 2>&1 || true
  docker buildx build \
    --platform "$DOCKER_PLATFORM" \
    -f "$DOCKERFILE" \
    -t "product-reviews:${IMAGE_TAG}" \
    --load \
    .
else
  docker build -f "$DOCKERFILE" -t "product-reviews:${IMAGE_TAG}" .
fi

docker tag "product-reviews:${IMAGE_TAG}" "${ECR_REPO_URI}:${IMAGE_TAG}"
docker push "${ECR_REPO_URI}:${IMAGE_TAG}"

echo "Pushed ${ECR_REPO_URI}:${IMAGE_TAG}"
