#!/usr/bin/env bash
set -euo pipefail

APP_NAME="reviewray"
PORT="${PORT:-8000}"

echo "=== ReviewRay Deploy ==="

# Check Python version
python3 --version || { echo "Python 3.11+ required"; exit 1; }

# Check uv
if ! command -v uv &>/dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "Installing dependencies..."
uv sync --no-dev

echo "Starting $APP_NAME on port $PORT..."
exec uv run uvicorn reviewray.main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --workers 2 \
    --log-level info
