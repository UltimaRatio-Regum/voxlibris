#!/bin/bash
set -e

PYTHON_PID=""
NODE_PID=""

cleanup() {
    echo "Shutting down..."
    if [ -n "$NODE_PID" ] && kill -0 "$NODE_PID" 2>/dev/null; then
        kill "$NODE_PID" 2>/dev/null || true
        wait "$NODE_PID" 2>/dev/null || true
    fi
    if [ -n "$PYTHON_PID" ] && kill -0 "$PYTHON_PID" 2>/dev/null; then
        kill "$PYTHON_PID" 2>/dev/null || true
        wait "$PYTHON_PID" 2>/dev/null || true
    fi
    exit 0
}

trap cleanup SIGTERM SIGINT

echo "Starting Python FastAPI backend..."
cd /app/backend
python main.py &
PYTHON_PID=$!
cd /app

echo "Waiting for Python backend to be ready..."
RETRIES=30
while [ $RETRIES -gt 0 ]; do
    if curl -sf http://127.0.0.1:8000/health > /dev/null 2>&1; then
        echo "Python backend is ready."
        break
    fi
    RETRIES=$((RETRIES - 1))
    sleep 1
done

if [ $RETRIES -eq 0 ]; then
    echo "WARNING: Python backend did not respond to health check, starting Node.js anyway..."
fi

echo "Starting Node.js server on port ${PORT:-5000}..."
node dist/index.cjs &
NODE_PID=$!

wait -n "$PYTHON_PID" "$NODE_PID" 2>/dev/null || true
cleanup
