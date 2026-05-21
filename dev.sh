#!/bin/bash
# Laffybot development launcher (Linux/macOS)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

BACKEND_PORT=8000
FRONTEND_PORT=1420

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --tauri      Start Tauri desktop instead of web frontend"
    echo "  --backend    Start backend only"
    echo "  --frontend   Start web frontend only"
    echo "  --help       Show this help"
    echo ""
    echo "Examples:"
    echo "  $0              Start backend + web frontend"
    echo "  $0 --tauri      Start backend + Tauri desktop"
    echo "  $0 --backend    Start backend only"
    exit 0
}

TAURI_MODE=false
BACKEND_ONLY=false
FRONTEND_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --tauri)
            TAURI_MODE=true
            shift
            ;;
        --backend)
            BACKEND_ONLY=true
            shift
            ;;
        --frontend)
            FRONTEND_ONLY=true
            shift
            ;;
        --help|-h)
            usage
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

cleanup() {
    echo ""
    echo "[Shutdown] Stopping processes..."
    if [[ -n "$BACKEND_PID" ]]; then
        kill $BACKEND_PID 2>/dev/null || true
    fi
    if [[ -n "$FRONTEND_PID" ]]; then
        kill $FRONTEND_PID 2>/dev/null || true
    fi
    wait 2>/dev/null
    echo "[Shutdown] Done."
    exit 0
}

trap cleanup SIGINT SIGTERM

if $BACKEND_ONLY && $FRONTEND_ONLY; then
    echo "Error: --backend and --frontend are mutually exclusive"
    exit 1
fi

if $FRONTEND_ONLY; then
    echo "[Frontend] Starting Vite dev server on port $FRONTEND_PORT..."
    cd ui && pnpm run dev
elif $BACKEND_ONLY; then
    echo "[Backend] Starting on port $BACKEND_PORT..."
    uv run laffybot --config config.json
else
    echo "[Backend] Starting on port $BACKEND_PORT..."
    uv run laffybot --config config.json &
    BACKEND_PID=$!

    sleep 2

    if ! kill -0 $BACKEND_PID 2>/dev/null; then
        echo "Error: Backend failed to start"
        exit 1
    fi

    if $TAURI_MODE; then
        echo "[Tauri] Starting Tauri dev mode..."
        cd ui && pnpm run tauri dev &
    else
        echo "[Frontend] Starting Vite dev server on port $FRONTEND_PORT..."
        cd ui && pnpm run dev &
    fi
    FRONTEND_PID=$!

    wait
fi
