#!/bin/bash
set -e

case "$1" in
  server)
    echo "Starting Argus server on ${APP_HOST:-0.0.0.0}:${APP_PORT:-8000}..."
    exec python -m uvicorn app.main:app \
      --host "${APP_HOST:-0.0.0.0}" \
      --port "${APP_PORT:-8000}" \
      --log-level "${LOG_LEVEL:-info}"
    ;;
  cli)
    shift
    exec argus "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
