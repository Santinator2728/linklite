#!/usr/bin/env bash
# Start the three LinkLite services locally without Docker (for development and demos).
# Requires the virtual environment from the README (.venv). Stop with Ctrl+C.
#
#   link       http://localhost:8001   (API docs: http://localhost:8001/docs)
#   redirect   http://localhost:8000
#   analytics  http://localhost:8003   (API docs: http://localhost:8003/docs)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UVICORN="$ROOT/.venv/bin/uvicorn"
DATA_DIR="$ROOT/.local-data"
mkdir -p "$DATA_DIR"

trap 'kill 0' EXIT

(cd "$ROOT/services/link" && LINK_DB_PATH="$DATA_DIR/links.db" \
    "$UVICORN" link_service.main:create_app --factory --port 8001) &
(cd "$ROOT/services/analytics" && CLICK_DB_PATH="$DATA_DIR/clicks.db" \
    "$UVICORN" analytics_service.main:create_app --factory --port 8003) &
(cd "$ROOT/services/redirect" && \
    "$UVICORN" redirect_service.main:create_app --factory --port 8000) &

wait
