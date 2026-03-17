#!/usr/bin/env bash
set -euo pipefail

APP_NAME="reviewray"

echo "=== ReviewRay Docker Deploy ==="

if command -v docker compose &>/dev/null; then
    COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
    COMPOSE="docker-compose"
else
    echo "Error: docker compose not found"
    exit 1
fi

echo "Building image..."
$COMPOSE build

echo "Starting container..."
$COMPOSE up -d

echo "Waiting for health check..."
for i in $(seq 1 10); do
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        echo "ReviewRay is running at http://localhost:8000"
        exit 0
    fi
    sleep 2
done

echo "Warning: health check failed, check logs:"
$COMPOSE logs --tail 20
exit 1
