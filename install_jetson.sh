#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_USER="${SUDO_USER:-$USER}"
VENV_DIR="$APP_DIR/.venv"
SUDOERS_FILE="/etc/sudoers.d/wifi-measurement"

if [ "$EUID" -eq 0 ]; then
  echo "Run this script as the Jetson login user, without sudo."
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This installer supports Ubuntu/Debian systems using apt-get."
  exit 1
fi

echo "Installing system packages..."
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip network-manager iputils-ping iw

echo "Creating Python virtual environment..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$APP_DIR/web_measurement_app/requirements.txt"

mkdir -p "$APP_DIR/logs"

# The application invokes `sudo nmcli` to read the connected Wi-Fi state.
echo "Configuring passwordless nmcli access for $APP_USER..."
printf '%s\n' "$APP_USER ALL=(root) NOPASSWD: /usr/bin/nmcli" | sudo tee "$SUDOERS_FILE" >/dev/null
sudo chmod 440 "$SUDOERS_FILE"
sudo visudo -cf "$SUDOERS_FILE"

echo
echo "Installation completed."
echo "Start the application with: ./start_jetson.sh"
echo "Open: http://<Jetson-IP>:9000"
