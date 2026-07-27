#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_USER="${SUDO_USER:-$USER}"
APP_GROUP="$(id -gn "$APP_USER")"
PYTHON="$APP_DIR/.venv/bin/python"
SERVICE_FILE="/etc/systemd/system/wifi-measurement.service"

if [ "$EUID" -eq 0 ]; then
  echo "Run this script as the Jetson login user, without sudo."
  exit 1
fi

if [ ! -x "$PYTHON" ]; then
  echo "Virtual environment not found. Run ./install_jetson.sh first."
  exit 1
fi

if [[ "$APP_DIR" == *$'\n'* || "$APP_DIR" == *' '* ]]; then
  echo "The application directory must not contain spaces or newline characters."
  exit 1
fi

sudo tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=Wi-Fi Measurement Dashboard
After=network-online.target NetworkManager.service
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_GROUP
WorkingDirectory=$APP_DIR
ExecStart=$PYTHON -m uvicorn web_measurement_app.server:app --host 0.0.0.0 --port 9000
Restart=on-failure
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now wifi-measurement.service
sudo systemctl status --no-pager wifi-measurement.service
