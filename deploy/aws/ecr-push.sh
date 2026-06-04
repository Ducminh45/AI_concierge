#!/usr/bin/env bash
# =============================================================================
# ECR Push Script — Build and push Docker image to Amazon ECR
# =============================================================================
#
# Usage:
#   ./deploy/aws/ecr-push.sh <account-id> <region> [tag]
#
# Example:
#   ./deploy/aws/ecr-push.sh 123456789012 eu-west-2 v1.2.0
# =============================================================================

set -euo pipefail

ACCOUNT_ID="${1:?Usage: $0 <account-id> <region> [tag]}"
REGION="${2:?Usage: $0 <account-id> <region> [tag]}"
TAG="${3:-latest}"

REPO_NAME="monster-resort-concierge"
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO_NAME}"

echo "==> Authenticating with ECR..."
aws ecr get-login-password --region "${REGION}" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo "==> Creating repository if it doesn't exist..."
aws ecr describe-repositories --repository-names "${REPO_NAME}" --region "${REGION}" 2>/dev/null \
  || aws ecr create-repository --repository-name "${REPO_NAME}" --region "${REGION}" \
       --image-scanning-configuration scanOnPush=true

echo "==> Building Docker image..."
docker build -t "${REPO_NAME}:${TAG}" .

echo "==> Tagging image..."
docker tag "${REPO_NAME}:${TAG}" "${ECR_URI}:${TAG}"

echo "==> Pushing to ECR..."
docker push "${ECR_URI}:${TAG}"

echo "==> Done! Image pushed to ${ECR_URI}:${TAG}"
