#!/bin/bash
# Startup script for the News Dashboard Backend on Render

set -e

echo "=== News Dashboard Backend Startup ==="
echo "Starting uvicorn server..."

# Use the PORT provided by Render (default 8001 for local dev)
PORT="${PORT:-8001}"

# Start the server
exec uvicorn main:app --host 0.0.0.0 --port "$PORT" --log-level info
