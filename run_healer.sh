#!/usr/bin/env bash
set -eo pipefail

# ==============================================================================
# CareerOps - Autonomous Post-Run Health Checkup & Stabilization Healer
# Independent Cron Wrapper for Catch-Up Submissions and Failure Remediation
# ==============================================================================

PROJECT_DIR="/u01/CareerOps"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/healer_run.log"
LOCK_FILE="/tmp/careerops.lock"
HEALER_LOCK_FILE="/tmp/careerops_healer_wrapper.lock"
MAX_LOG_SIZE=10485760 # 10 MB

mkdir -p "$LOG_DIR"

# Check if main pipeline is actively running. If so, exit gracefully to prevent OOM
if fuser "$LOCK_FILE" >/dev/null 2>&1; then
    echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] Main CareerOps pipeline is currently active. Yielding to prevent OOM." >> "$LOG_FILE"
    exit 0
fi

# Acquire healer lock to prevent concurrent healer executions
exec 201>"$HEALER_LOCK_FILE"
if ! flock -n 201; then
    echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] Another healer instance is already running. Exiting." >> "$LOG_FILE"
    exit 0
fi

# Rotate log file if > 10MB
if [ -f "$LOG_FILE" ]; then
    CURRENT_SIZE=$(wc -c < "$LOG_FILE" 2>/dev/null || echo 0)
    if [ "$CURRENT_SIZE" -gt "$MAX_LOG_SIZE" ]; then
        tail -n 5000 "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
    fi
fi

cd "$PROJECT_DIR"

# Environment
export PYTHONPATH="$PROJECT_DIR"
export PATH="$PROJECT_DIR/venv/bin:$PATH"
export PYTHONUNBUFFERED=1

# Weekend check: Only run Mon-Fri
DOW=$(TZ="Asia/Kolkata" date +%u)
if [ "$DOW" -gt 5 ]; then
    exit 0
fi

# Ensure Xvfb is available for browser-based catch-up submissions
if ! pgrep -x "Xvfb" > /dev/null 2>&1; then
    Xvfb :99 -screen 0 1920x1080x24 -ac 201>&- >/dev/null 2>&1 &
    sleep 1
fi
export DISPLAY=:99
export HEADLESS=false

echo "==============================================================================" >> "$LOG_FILE"
echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] CareerOps Autonomous Healer Cron Invoked" >> "$LOG_FILE"

START_TIME=$(date +%s)
set +e
timeout 90m nice -n 10 "$PROJECT_DIR/venv/bin/python" -m src.agents.post_run_healer "$@" >> "$LOG_FILE" 2>&1
EXIT_CODE=$?
set -e
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] Healer Completed in ${DURATION}s with exit code ${EXIT_CODE}" >> "$LOG_FILE"
echo "==============================================================================" >> "$LOG_FILE"

exit $EXIT_CODE
