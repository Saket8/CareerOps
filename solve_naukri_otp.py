import imaplib
import email
import re
import os
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

username = os.environ.get("NAUKRI_USERNAME", "")
password = os.environ.get("NAUKRI_PASSWORD", "")
smtp_user = os.environ.get("SMTP_USERNAME", "")
smtp_pass = os.environ.get("SMTP_PASSWORD", "")

if "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":99"

def fetch_latest_naukri_otp(start_time: float, timeout_sec: int = 60) -> str:
    print(f"Waiting for Naukri OTP email in {smtp_user} (timeout {timeout_sec}s)...")
    end_time = time.time() + timeout_sec
    while time.time() < end_time:
        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(smtp_user, smtp_pass)
            mail.select("inbox")
            status, messages = mail.search(None, '(FROM "naukri" SUBJECT "OTP")')
            msg_ids = messages[0].split()
            if msg_ids:
                for mid in reversed(msg_ids[-5:]):
                    res, data = mail.fetch(mid, "(RFC822)")
                    for part in data:
                        if isinstance(part, tuple):
                            msg = email.message_from_bytes(part[1])
                            body = ""
                            for p in msg.walk():
                                pl = p.get_payload(decode=True)
                                if pl:
                                    body += " " + pl.decode(errors="ignore")
                            clean = ' '.join(re.sub(r'<[^>]+>', ' ', body).split())
                            m = re.search(r"enter below OTP.*?(\d{6})", clean, re.I)
                            if not m:
                                m = re.search(r"valid for the next.*?(\d{6})", clean, re.I)
                            if not m:
                                m = re.search(r"\b(\d{6})\b", clean)
                            if m:
                                otp = m.group(1)
                                print(f"Successfully retrieved OTP: {otp} from email: {msg.get('Subject')} ({msg.get('Date')})")
                                mail.close()
                                mail.logout()
                                return otp
            mail.close()
            mail.logout()
        except Exception as e:
            print(f"IMAP poll error: {e}")
        time.sleep(3)
    raise TimeoutError("Timed out waiting for Naukri OTP email")

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ]
    )
    context = browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080}
    )
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
    """)
    page = context.new_page()

    login_url = "https://www.naukri.com/nlogin/login"
    print(f"Navigating to {login_url}...")
    page.goto(login_url, wait_until="domcontentloaded", timeout=35000)
    page.wait_for_timeout(2000)

    user_field = page.locator("#usernameField")
    pass_field = page.locator("#passwordField")
    if user_field.count() > 0 and pass_field.count() > 0:
        print("Filling credentials...")
        user_field.fill(username)
        pass_field.fill(password)
        time_before_click = time.time()
        
        login_btn = page.locator("button:has-text('Login'), button.blue-btn").first
        login_btn.click()
        page.wait_for_timeout(4000)
        
        # Check for OTP inputs
        inp1 = page.locator("#Input_1")
        if inp1.count() > 0:
            print("OTP inputs #Input_1 through #Input_6 detected!")
            
            # Fetch latest OTP from Gmail
            otp_code = fetch_latest_naukri_otp(time_before_click, timeout_sec=60)
            print(f"Typing OTP code: {otp_code} into #Input_1..#Input_6...")

            for i in range(1, 7):
                digit = otp_code[i - 1]
                input_el = page.locator(f"#Input_{i}")
                input_el.click()
                input_el.fill(digit)
                page.wait_for_timeout(150)

            page.wait_for_timeout(1000)
            page.screenshot(path="otp_filled.png")

            # Click Verify button
            verify_btn = page.locator("button.verify-button, button:has-text('Verify')").first
            print("Verify button disabled:", "button-disabled" in (verify_btn.get_attribute("class") or ""))
            print("Clicking Verify button...")
            verify_btn.click()
            page.wait_for_timeout(6000)
            
            print("Post-verify URL:", page.url)
            print("Post-verify Title:", page.title())
            page.screenshot(path="post_verify.png")

            # Verify login success
            profile_indicators = page.locator(".nI-gNb-drawer, .view-profile-wrapper, a[href*='profile'], .nI-gNb-header")
            print("Profile indicators count:", profile_indicators.count())

            if "mnjuser" in page.url or "myapply" in page.url or profile_indicators.count() > 0:
                print("LOGIN SUCCESSFUL! Saving storage state to artifacts/naukri_auth.json...")
                context.storage_state(path="artifacts/naukri_auth.json")
                print("Storage state successfully saved to artifacts/naukri_auth.json!")
            else:
                errs = page.locator(".server-err, .err, [class*='error']").all_text_contents()
                print("Errors found:", errs)

    browser.close()
