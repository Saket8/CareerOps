import sys
import json
import urllib.request
from playwright.sync_api import sync_playwright

def test_urllib():
    print("--- 1. Testing urllib ---")
    req = urllib.request.Request(
        "https://www.naukri.com/oracle-cloud-infrastructure-architect-jobs",
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print("urllib status:", resp.status)
            body = resp.read(500).decode("utf-8", errors="ignore")
            print("urllib body preview:", body[:150])
    except Exception as e:
        print("urllib error:", e)

def test_playwright_stealth():
    print("\n--- 2. Testing Playwright with evasions ---")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--window-size=1920,1080",
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

        # Anti-detection stealth script
        stealth_js = """
        // Overwrite the `navigator.webdriver` property
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });

        // Mock window.chrome
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };

        // Mock plugins and languages
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });

        // Mock permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        """
        page = context.new_page()
        page.add_init_script(stealth_js)

        # Test request API first
        print("Testing context.request.get...")
        api_resp = context.request.get("https://www.naukri.com/oracle-cloud-infrastructure-architect-jobs")
        print("Playwright context.request status:", api_resp.status)

        # Now test page.goto
        url = "https://www.naukri.com/oracle-cloud-infrastructure-architect-jobs"
        print("Testing page.goto:", url)
        page.on("console", lambda msg: print(f"CONSOLE: [{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
        page.on("requestfailed", lambda req: print(f"REQUEST FAILED: {req.url} -> {req.failure}"))

        resp = page.goto(url, timeout=30000, wait_until="load")
        print("Playwright page status:", resp.status if resp else "None")
        page.wait_for_timeout(5000)
        print("Page title after 5s:", page.title())
        page.screenshot(path="page_view2.png")

        # Check various selectors
        selectors = [
            "div.cust-job-tuple",
            "div.srp-jobtuple",
            "article.jobTuple",
            "div[data-job-id]",
            "div.styles_job-listing-container__",
            "div.list",
            "a.title",
        ]
        for sel in selectors:
            cnt = page.locator(sel).count()
            print(f"Selector '{sel}': {cnt}")

        if page.locator("div.cust-job-tuple, div.srp-jobtuple").count() > 0:
            first_title = page.locator("div.cust-job-tuple a.title, div.srp-jobtuple a.title").first.inner_text()
            print("First job title found:", first_title)

        browser.close()

if __name__ == "__main__":
    test_urllib()
    test_playwright_stealth()
