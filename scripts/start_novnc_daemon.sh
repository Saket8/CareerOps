#!/bin/bash
# Clean background launcher for noVNC + Persistent Browser
set -e

# Kill any stale websockify or launch_browser processes
pkill -f "websockify.*6080" || true
pkill -f "launch_browser_session.py" || true

# Start websockify in background nohup
nohup websockify --web /usr/share/novnc 6080 localhost:5900 > /u01/CareerOps/artifacts/websockify.log 2>&1 &

# Start the interactive browser in background nohup
DISPLAY=:99 nohup /home/opc/CareerOps/venv/bin/python3 /u01/CareerOps/scripts/launch_browser_session.py > /u01/CareerOps/artifacts/browser_session.log 2>&1 &

sleep 2
echo "Active processes:"
ps aux | grep -E "websockify|launch_browser|x11vnc" | grep -v grep
