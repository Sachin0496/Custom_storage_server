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

# Open browser after short delay
( sleep 1.5 && open "http://localhost:8080" ) &

# Start server using venv
.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8080
