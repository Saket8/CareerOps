#!/bin/bash
set -e

# Start Xvfb if not already running
if ! pgrep -f "Xvfb :99" > /dev/null; then
    echo "Starting Xvfb on :99..."
    Xvfb :99 -screen 0 1920x1080x24 -ac &
    sleep 2
fi

export DISPLAY=:99
cd /home/opc/CareerOps

echo "Running test_login_vps.py..."
/home/opc/CareerOps/venv/bin/python test_login_vps.py
