#!/usr/bin/env bash
set -eo pipefail

# ==============================================================================
# CareerOps - Autonomous Naukri Career Intelligence Agent
# OOM-Safe Cron Execution Wrapper for Low-Resource OCI Linux VPS
# ==============================================================================

PROJECT_DIR="/home/opc/CareerOps"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/cron_run.log"
LOCK_FILE="/tmp/careerops.lock"
MAX_LOG_SIZE=10485760 # 10 MB

mkdir -p "$LOG_DIR"

# Prevent concurrent runs to protect the 945 MB RAM server from OOM spikes
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] Another CareerOps run is already active. Exiting immediately to prevent OOM." >> "$LOG_FILE"
    exit 0
fi

# Log size rotation/truncation guard (keep last 5000 lines if > 10MB)
if [ -f "$LOG_FILE" ]; then
    CURRENT_SIZE=$(wc -c < "$LOG_FILE" 2>/dev/null || echo 0)
    if [ "$CURRENT_SIZE" -gt "$MAX_LOG_SIZE" ]; then
        tail -n 5000 "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
    fi
fi

cd "$PROJECT_DIR"

# Export Environment
export PYTHONPATH="$PROJECT_DIR"
export PATH="$PROJECT_DIR/venv/bin:$PATH"
export PYTHONUNBUFFERED=1

# Manage lightweight Xvfb virtual framebuffer on :99 to bypass Akamai 403 Bot Detection
if ! pgrep -x "Xvfb" > /dev/null 2>&1; then
    echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] Starting Xvfb virtual display on :99..." >> "$LOG_FILE"
    Xvfb :99 -screen 0 1920x1080x24 -ac 200>&- >/dev/null 2>&1 &
    sleep 1
fi
export DISPLAY=:99
export HEADLESS=false

# Weekend Check: Saturday & Sunday (Asia/Kolkata timezone: 1=Mon ... 5=Fri, 6=Sat, 7=Sun)
# Weekends execute ONLY Naukri master resume refresh to maintain Resdex rank (nothing else).
DOW=$(TZ="Asia/Kolkata" date +%u)
if [ "$DOW" -gt 5 ]; then
    echo "==============================================================================" >> "$LOG_FILE"
    echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] Weekend detected (day $DOW). Executing ONLY Naukri profile resume refresh..." >> "$LOG_FILE"
    echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] Initial Memory Status:" >> "$LOG_FILE"
    free -h >> "$LOG_FILE"

    START_TIME=$(date +%s)
    set +e
    nice -n 10 "$PROJECT_DIR/venv/bin/python" "$PROJECT_DIR/main.py" --refresh-profile >> "$LOG_FILE" 2>&1
    EXIT_CODE=$?
    set -e
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] Weekend Naukri Resume Refresh Completed in ${DURATION}s with exit code ${EXIT_CODE}" >> "$LOG_FILE"
    echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] Post-Run Memory Status:" >> "$LOG_FILE"
    free -h >> "$LOG_FILE"
    echo "==============================================================================" >> "$LOG_FILE"
    exit $EXIT_CODE
fi

echo "==============================================================================" >> "$LOG_FILE"
echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] CareerOps Weekday Pipeline Started" >> "$LOG_FILE"
echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] Initial Memory Status:" >> "$LOG_FILE"
free -h >> "$LOG_FILE"

# Run Autonomous Career Agent Pipeline (Mon-Fri)
START_TIME=$(date +%s)
set +e
nice -n 10 "$PROJECT_DIR/venv/bin/python" "$PROJECT_DIR/main.py" "$@" >> "$LOG_FILE" 2>&1
EXIT_CODE=$?
set -e
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] CareerOps Run Completed in ${DURATION}s with exit code ${EXIT_CODE}" >> "$LOG_FILE"

# Post-Run Health Checkup, Failure Diagnosis & Autonomous Stabilization Healer
echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] Starting Autonomous Post-Run Healer & Verification..." >> "$LOG_FILE"
set +e
nice -n 10 "$PROJECT_DIR/venv/bin/python" -m src.agents.post_run_healer --post-run >> "$LOG_FILE" 2>&1
HEALER_EXIT=$?
set -e
echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] Post-Run Healer Completed with exit code ${HEALER_EXIT}" >> "$LOG_FILE"

echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] Post-Run Memory Status:" >> "$LOG_FILE"
free -h >> "$LOG_FILE"
echo "==============================================================================" >> "$LOG_FILE"

exit $EXIT_CODE
