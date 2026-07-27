#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$APP_DIR/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  echo "Virtual environment not found. Run ./install_jetson.sh first."
  exit 1
fi

cd "$APP_DIR"
mkdir -p logs
exec "$PYTHON" -m uvicorn web_measurement_app.server:app --host 0.0.0.0 --port 9000
