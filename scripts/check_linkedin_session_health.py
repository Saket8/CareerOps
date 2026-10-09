#!/usr/bin/env python3
"""
LinkedIn Session Health Checker & Auto-Trigger
1. Validates whether the persistent session in /u01/CareerOps/.li_profile (or artifacts/linkedin_auth.json) is active.
2. If expired or unauthenticated:
   - Auto-opens port 6080 to the user's IP for 15 minutes.
   - Sends an alert with the noVNC direct URL.
3. If valid: logs success and exits clean.
"""

import sys
import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

USER_DATA_DIR = "/u01/CareerOps/.li_profile"
AUTH_FILE = Path("/u01/CareerOps/artifacts/linkedin_auth.json")

def check_health():
    print("[HealthCheck] Checking LinkedIn session status...")
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled'],
            viewport={'width': 1280, 'height': 800}
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(4)
        
        url = page.url
        is_logged_in = "feed" in url and "login" not in url and "checkpoint" not in url
        print(f"[HealthCheck] Current URL: {url} | Is Authenticated: {is_logged_in}")
        
        if is_logged_in:
            context.storage_state(path=str(AUTH_FILE))
            print("[HealthCheck] Session is HEALTHY. State exported to", AUTH_FILE)
            context.close()
            return True
        else:
            print("[HealthCheck] Session is EXPIRED or UNAUTHENTICATED.")
            context.close()
            return False

if __name__ == "__main__":
    healthy = check_health()
    if not healthy:
        # Trigger noVNC open script
        import subprocess
        print("[HealthCheck] Triggering open_novnc_access.sh...")
        subprocess.run(["/u01/CareerOps/scripts/open_novnc_access.sh"])
        sys.exit(1)
    sys.exit(0)
