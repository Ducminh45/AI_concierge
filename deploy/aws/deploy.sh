#!/usr/bin/env bash
# =============================================================================
# ECS Deploy Script — Register task definition and update ECS service
# =============================================================================
#
# Usage:
#   ./deploy/aws/deploy.sh <account-id> <region> [cluster] [service]
#
# Example:
#   ./deploy/aws/deploy.sh 123456789012 eu-west-2 monster-resort monster-resort-api
# =============================================================================

set -euo pipefail

ACCOUNT_ID="${1:?Usage: $0 <account-id> <region> [cluster] [service]}"
REGION="${2:?Usage: $0 <account-id> <region> [cluster] [service]}"
CLUSTER="${3:-monster-resort}"
SERVICE="${4:-monster-resort-api}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TASK_DEF_FILE="${SCRIPT_DIR}/ecs-task-definition.json"

echo "==> Preparing task definition..."
# Replace placeholder values in the task definition
TASK_DEF=$(cat "${TASK_DEF_FILE}" \
  | sed "s/ACCOUNT_ID/${ACCOUNT_ID}/g" \
  | sed "s/REGION/${REGION}/g")

echo "==> Registering task definition..."
TASK_ARN=$(echo "${TASK_DEF}" | aws ecs register-task-definition \
  --region "${REGION}" \
  --cli-input-json file:///dev/stdin \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text)

echo "    Registered: ${TASK_ARN}"

echo "==> Updating ECS service..."
aws ecs update-service \
  --region "${REGION}" \
  --cluster "${CLUSTER}" \
  --service "${SERVICE}" \
  --task-definition "${TASK_ARN}" \
  --force-new-deployment \
  --query 'service.serviceName' \
  --output text

echo "==> Waiting for service to stabilise..."
aws ecs wait services-stable \
  --region "${REGION}" \
  --cluster "${CLUSTER}" \
  --services "${SERVICE}"

echo "==> Deployment complete! Service ${SERVICE} is stable."
