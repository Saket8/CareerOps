#!/bin/bash
# Enable noVNC access for the user's specific IP for 15 minutes, then close it automatically.
set -e

USER_IP="$1"
DURATION_MINUTES="${2:-15}"

if [ -z "$USER_IP" ]; then
    # Auto-detect from SSH if available
    USER_IP=$(echo "$SSH_CLIENT" | awk '{print $1}')
fi

if [ -z "$USER_IP" ]; then
    # Fallback to known user IP
    USER_IP="122.161.78.108"
fi

echo "[$(date)] Opening port 6080 to ${USER_IP} for ${DURATION_MINUTES} minutes..."

# 1. Start Xvfb if not running
if ! pgrep -f "Xvfb :99" > /dev/null; then
    echo "Starting Xvfb on display :99..."
    Xvfb :99 -screen 0 1600x900x24 -ac &
    sleep 2
fi

# 2. Start openbox window manager if not running
if ! pgrep -f "openbox" > /dev/null; then
    echo "Starting openbox..."
    DISPLAY=:99 openbox &
    sleep 1
fi

# 3. Start x11vnc if not running
if ! pgrep -f "x11vnc.*:99" > /dev/null; then
    echo "Starting x11vnc on :99 (port 5900)..."
    x11vnc -display :99 -nopw -forever -shared -bg -rfbport 5900 -quiet
    sleep 1
fi

# 4. Start websockify / noVNC if not running
if ! pgrep -f "websockify.*6080" > /dev/null; then
    echo "Starting websockify on port 6080 -> 5900 with noVNC web assets..."
    websockify --web /usr/share/novnc 6080 localhost:5900 &
    sleep 2
fi

# 5. Open port 6080 in firewalld specifically for USER_IP
echo "Applying firewalld rich rule for ${USER_IP}..."
sudo firewall-cmd --add-rich-rule="rule family='ipv4' source address='${USER_IP}' port port='6080' protocol='tcp' accept" --timeout="${DURATION_MINUTES}m"

# 6. Launch browser on DISPLAY=:99 in background if not already active
if ! pgrep -f "launch_browser_session.py" > /dev/null; then
    echo "Launching persistent LinkedIn browser on DISPLAY=:99..."
    DISPLAY=:99 /home/opc/CareerOps/venv/bin/python3 /u01/CareerOps/scripts/launch_browser_session.py &
fi

SERVER_IP=$(curl -s https://api.ipify.org)
NOVNC_URL="http://${SERVER_IP}:6080/vnc.html?autoconnect=true&resize=scale"

echo "=========================================================="
echo "noVNC IS LIVE AND SECURED!"
echo "Access restricted to: ${USER_IP}"
echo "Expires in: ${DURATION_MINUTES} minutes"
echo "URL: ${NOVNC_URL}"
echo "=========================================================="
