#!/usr/bin/env bash
# LAN Store — macOS/Linux Launcher
set -e
cd "$(dirname "$0")"

echo ""
echo "  ⚡ LAN Store — Starting..."
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "  ❌ Python 3 is required. Download it from https://python.org"
  exit 1
fi

# Create virtualenv if needed
if [ ! -d ".venv" ]; then
  echo "  Setting up environment (first run only)..."
  python3 -m venv .venv
fi

# Install deps silently into venv
.venv/bin/pip install -r requirements.txt -q --disable-pip-version-check

# Ensure a portable writable shared drive exists and is mapped
.venv/bin/python bootstrap_portable.py

PORT=$(python3 -c "import json; print(json.load(open('config.json')).get('port', 8080))")
# Open browser after short delay
(
  sleep 1.5
  if command -v open >/dev/null 2>&1; then
    open "http://localhost:$PORT" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "http://localhost:$PORT" >/dev/null 2>&1 || true
  fi
) &

# Start server using venv
.venv/bin/python main.py
