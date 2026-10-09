import os
import glob
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

USER_DATA_DIR = "/u01/CareerOps/.li_profile"
AUTH_FILE = "/u01/CareerOps/artifacts/linkedin_auth.json"
EVIDENCE_DIR = "/u01/CareerOps/artifacts/evidence"
os.makedirs(EVIDENCE_DIR, exist_ok=True)

# Clean up stale Chromium lock files
for lock in glob.glob(f"{USER_DATA_DIR}/Singleton*"):
    try:
        os.remove(lock)
        print(f"Removed stale lock: {lock}")
    except Exception:
        pass

print("Launching persistent Chromium browser on DISPLAY=:99...")
with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=USER_DATA_DIR,
        headless=False,
        args=[
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--start-maximized',
            '--disable-blink-features=AutomationControlled'
        ],
        viewport={'width': 1600, 'height': 900}
    )
    page = context.pages[0] if context.pages else context.new_page()
    page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
    print("Browser navigated to https://www.linkedin.com/login")
    print("Persistent session directory:", USER_DATA_DIR)
    print("Browser is ready for user manual login via noVNC.")
    
    saved_once = False
    start_time = time.time()
    max_duration = 3600  # Keep open for 60 minutes so user has plenty of time
    
    print("Browser is open and running on noVNC. Please sign in via the web window.")
    
    try:
        while time.time() - start_time < max_duration:
            time.sleep(3)
            current_url = page.url
            
            # Check for genuine post-login navigation (feed, jobs, profile, network)
            is_post_login = any(k in current_url for k in ["/feed", "/jobs", "/mynetwork", "/in/"]) and "login" not in current_url and "checkpoint" not in current_url and "authwall" not in current_url

            if is_post_login:
                cookies = context.cookies()
                has_active_li_at = any(c['name'] == 'li_at' and c['value'] for c in cookies)
                
                if has_active_li_at:
                    context.storage_state(path=AUTH_FILE)
                    
                    if not saved_once:
                        print(f"[AUTH CONFIRMED] Authenticated page reached: {current_url}")
                        print(f"[SUCCESS] Session saved to {AUTH_FILE}")
                        try:
                            page.screenshot(path=f"{EVIDENCE_DIR}/linkedin_login_success.png")
                        except Exception:
                            pass
                        Path("/u01/CareerOps/artifacts/linkedin_authenticated.flag").touch()
                        saved_once = True
                    
                    # Keep saving updated cookies every 30s while user browses
                    time.sleep(15)
                    context.storage_state(path=AUTH_FILE)
    except KeyboardInterrupt:
        print("Closing browser context...")
    finally:
        if saved_once:
            context.storage_state(path=AUTH_FILE)
        context.close()
        print("Browser session closed cleanly.")

