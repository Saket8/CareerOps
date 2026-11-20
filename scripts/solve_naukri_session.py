"""
Interactive Naukri Session Generator.
Submits login credentials, surfaces any Arkose challenge for human/agent visual solving,
handles OTP via IMAP, and persists the authenticated storage state to artifacts/naukri_auth.json.
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, "/u01/CareerOps")

# Ensure display is set
if sys.platform != "win32" and "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":99"

from dotenv import load_dotenv
load_dotenv()

from src.naukri.playwright_adapter import PlaywrightBrowserAdapter, AUTH_STATE_FILE
from playwright.sync_api import sync_playwright

def main():
    adapter = PlaywrightBrowserAdapter(offline_mode=False)
    username = os.environ.get("NAUKRI_USERNAME", "")
    password = os.environ.get("NAUKRI_PASSWORD", "")
    
    if not username or not password:
        print("ERROR: NAUKRI_USERNAME or NAUKRI_PASSWORD not configured in .env", flush=True)
        return

    print("Launching Chromium for Naukri authentication...", flush=True)
    with sync_playwright() as p:
        browser, context = adapter._launch_browser(p)
        page = context.new_page()
        
        print("Navigating to https://www.naukri.com/nlogin/login...", flush=True)
        page.goto("https://www.naukri.com/nlogin/login", timeout=45000, wait_until="domcontentloaded")
        
        print("Waiting for #usernameField...", flush=True)
        user_field = page.wait_for_selector("#usernameField", timeout=60000)
        user_field.click()
        user_field.fill(username)
        
        pass_field = page.wait_for_selector("#passwordField", timeout=15000)
        pass_field.click()
        pass_field.fill(password)
        
        t_click = time.time()
        print("Clicking Login button...", flush=True)
        login_btn = page.locator("button:has-text('Login'), button.blue-btn").first
        login_btn.click()
        
        # Wait up to 10 seconds for next state
        page.wait_for_timeout(7000)
        
        # Check if already authenticated (redirected to mnjuser)
        if "mnjuser" in page.url or any(c["name"] == "nauk_at" for c in context.cookies()):
            print("Direct authentication successful! Saving session...", flush=True)
            context.storage_state(path=str(AUTH_STATE_FILE))
            print("SESSION_SAVED_SUCCESSFULLY", flush=True)
            browser.close()
            return
            
        # Check for Arkose Captcha loop
        while True:
            captcha_card = page.locator(".captcha-modal-card")
            if captcha_card.count() > 0 and captcha_card.first.is_visible():
                q_pref = page.locator(".captcha-title-preface").inner_text().strip() if page.locator(".captcha-title-preface").count() > 0 else ""
                q_text = page.locator(".captcha-title-question").inner_text().strip() if page.locator(".captcha-title-question").count() > 0 else ""
                full_question = f"{q_pref} {q_text}".strip()
                
                # Check if it's the shape matching puzzle (buttons with text)
                shape_btns = page.locator(".captcha-modal-card button").all()
                shape_texts = [b.inner_text().strip() for b in shape_btns if b.inner_text().strip() and b.inner_text().strip().lower() not in ("verify", "")]
                
                screenshot_path = "artifacts/evidence/current_captcha_challenge.png"
                page.screenshot(path=screenshot_path)
                
                print(f"=== CAPTCHA DETECTED ===", flush=True)
                print(f"QUESTION: {full_question}", flush=True)
                if shape_texts:
                    print(f"SHAPE OPTIONS: {shape_texts}", flush=True)
                print(f"SCREENSHOT: {screenshot_path}", flush=True)
                print(f"WAITING_FOR_INPUT: Enter tile numbers 1-9 (e.g. '1,5,7') or shape name (e.g. 'Leaf'):", flush=True)
                
                user_input = sys.stdin.readline().strip()
                print(f"Received answer: {user_input}", flush=True)
                
                if user_input.lower() in ("abort", "exit", "quit"):
                    print("Aborting captcha solve.", flush=True)
                    browser.close()
                    return
                
                # If answer matches a shape option button
                matched_shape = False
                for b in shape_btns:
                    if b.inner_text().strip().lower() == user_input.lower():
                        print(f"Clicking shape button: {b.inner_text().strip()}", flush=True)
                        b.click()
                        matched_shape = True
                        break
                        
                if not matched_shape:
                    # Tile indices 1-9
                    try:
                        indices = [int(x.strip()) for x in user_input.split(",") if x.strip().isdigit()]
                        tiles = page.locator("button.captcha-grid-tile").all()
                        print(f"Clicking tiles: {indices} (total tiles available: {len(tiles)})", flush=True)
                        for idx in indices:
                            if 1 <= idx <= len(tiles):
                                tiles[idx - 1].click()
                                time.sleep(0.3)
                    except Exception as e:
                        print(f"Error clicking tiles: {e}", flush=True)
                
                time.sleep(1)
                # Click VERIFY button
                verify_btn = page.locator(".captcha-modal-card button:has-text('VERIFY'), .captcha-modal-card button:has-text('Verify')").first
                if verify_btn.count() > 0 and verify_btn.is_visible():
                    print("Clicking VERIFY button...", flush=True)
                    verify_btn.click()
                
                page.wait_for_timeout(6000)
                # Check if puzzle is solved or next round
                if page.locator(".captcha-modal-card").count() == 0 or not page.locator(".captcha-modal-card").first.is_visible():
                    print("Captcha modal dismissed! Proceeding to post-captcha state...", flush=True)
                    break
                else:
                    print("Next round of captcha detected, refreshing challenge info...", flush=True)
                    continue
            else:
                # No captcha card visible
                break
                
        # Check for OTP challenge
        otp_inp = page.locator("#Input_1")
        if (otp_inp.count() > 0 and otp_inp.first.is_visible()) or page.locator("button.verify-button").count() > 0:
            print("Naukri OTP challenge detected! Polling Gmail via IMAP...", flush=True)
            otp = adapter._fetch_naukri_otp(t_click - 15, timeout_sec=60)
            print(f"IMAP OTP result: {otp}", flush=True)
            if otp:
                for i in range(1, 7):
                    f = page.locator(f"#Input_{i}")
                    f.click()
                    f.fill(otp[i - 1])
                    time.sleep(0.15)
                time.sleep(1)
                vbtn = page.locator("button.verify-button, button:has-text('Verify')").first
                if vbtn.count() > 0:
                    print("Clicking Verify OTP button...", flush=True)
                    vbtn.click()
                    page.wait_for_timeout(8000)
            else:
                print("Failed to retrieve fresh OTP from Gmail via IMAP.", flush=True)
                
        # Final session assertion
        time.sleep(3)
        cookies = context.cookies()
        auth_cookie_names = [c["name"] for c in cookies if "nauk" in c["name"] or "MYNAUK" in c["name"]]
        print(f"Final session cookies: {auth_cookie_names}", flush=True)
        
        has_auth = (
            any(c["name"] in ("nauk_at", "nauk_rt", "nauk_sid") for c in cookies)
            or "mnjuser" in page.url
            or page.locator(".nI-gNb-drawer, .view-profile-wrapper, a[href*='mnjuser/profile']").count() > 0
        )
        
        if has_auth:
            context.storage_state(path=str(AUTH_STATE_FILE))
            print(f"SUCCESS: Logged-in session successfully persisted to {AUTH_STATE_FILE}!", flush=True)
            print("SESSION_SAVED_SUCCESSFULLY", flush=True)
        else:
            print("FAILED: Unable to verify authenticated session.", flush=True)
            page.screenshot(path="artifacts/evidence/final_failed_login.png")
            
        browser.close()

if __name__ == "__main__":
    main()
