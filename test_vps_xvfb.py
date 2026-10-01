import os
import subprocess
import time
from playwright.sync_api import sync_playwright

# Start Xvfb if not running
xvfb_proc = None
if "DISPLAY" not in os.environ or not os.environ["DISPLAY"]:
    print("Starting Xvfb on :99...")
    xvfb_proc = subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1920x1080x24", "-ac"])
    os.environ["DISPLAY"] = ":99"
    time.sleep(1)

try:
    with sync_playwright() as p:
        print("Launching Chromium with headless=False on DISPLAY", os.environ["DISPLAY"])
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
        page = context.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)
        
        url = "https://www.naukri.com/oracle-cloud-infrastructure-architect-jobs"
        print("Navigating to:", url)
        resp = page.goto(url, wait_until="domcontentloaded", timeout=35000)
        
        # Click cookie consent if present
        try:
            page.locator("button:has-text('Got it')").click(timeout=2000)
        except Exception:
            pass

        print("Waiting for job tuples to render...")
        try:
            page.wait_for_selector("div.cust-job-tuple, div.srp-jobtuple, article", timeout=15000)
        except Exception as e:
            print("Wait selector timed out:", e)
        
        page.wait_for_timeout(2000)
        print("Status:", resp.status if resp else "None")
        print("Title:", page.title())
        tuples = page.locator("div.cust-job-tuple, div.srp-jobtuple").count()
        print("Job tuples found on VPS:", tuples)
        
        if tuples > 0:
            first_title = page.locator("div.cust-job-tuple a.title, div.srp-jobtuple a.title").first.inner_text()
            print("First job title:", first_title)
            
            # Print first 3 jobs
            for i in range(min(5, tuples)):
                t = page.locator("div.cust-job-tuple, div.srp-jobtuple").nth(i)
                title = t.locator("a.title").first.inner_text() if t.locator("a.title").count() > 0 else "N/A"
                comp = t.locator("a.comp-name").first.inner_text() if t.locator("a.comp-name").count() > 0 else "N/A"
                print(f"  {i+1}. {title} @ {comp}")
        
        page.screenshot(path="xvfb_success2.png")
        print("Screenshot saved to xvfb_success.png")
        browser.close()
finally:
    if xvfb_proc:
        xvfb_proc.terminate()
        xvfb_proc.wait()
